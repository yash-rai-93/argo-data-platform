"""Manually refresh a bounded recent-activity snapshot, independently of training.

Only a successful query and validated snapshot can advance the cursor. The
workflow publishes both files on a review branch; main remains the durable
checkpoint. No schedule, warehouse rebuild, model training, or cloud storage.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "data"
_STATE_NAME = "recent-activity-state.json.gz"
_SUMMARY_NAME = "recent-activity.json"
MAX_DAYS = 31
RETAIN_DAYS = 90
OVERLAP_DAYS = 2
BOOTSTRAP_DAYS = 7
MAX_BYTES_BILLED = 20_000_000_000
MAX_STATE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Window:
    """Half-open UTC query range, plus continuity metadata."""

    start: date
    end: date
    coverage_start: date
    requested_end: date

    @property
    def caught_up(self) -> bool:
        return self.end == self.requested_end


def available_end(now: datetime) -> date:
    """Leave yesterday and the current UTC day for source publication."""
    return now.astimezone(UTC).date() - timedelta(days=1)


def plan_window(state: dict | None, end: date, now: datetime) -> Window | None:
    """Bootstrap recently, then advance at most 31 daily tables with overlap."""
    if end > available_end(now):
        raise ValueError("End date must leave yesterday and today unqueried (UTC).")
    if state is None:
        start = end - timedelta(days=BOOTSTRAP_DAYS)
        return Window(start, end, start, end)
    cursor = date.fromisoformat(state["through_exclusive"])
    coverage = date.fromisoformat(state["coverage_start"])
    if end < cursor:
        raise ValueError("End date precedes the approved cursor; rollback is refused.")
    if end == cursor:
        return None
    start = max(coverage, cursor - timedelta(days=OVERLAP_DAYS))
    effective_end = min(end, start + timedelta(days=MAX_DAYS))
    return Window(start, effective_end, coverage, end)


def render_sql(window: Window) -> str:
    """Use exact table identifiers; missing source days fail the entire query."""
    count = (window.end - window.start).days
    if not 0 < count <= MAX_DAYS:
        raise ValueError("Query must read between 1 and 31 daily tables.")
    selections = []
    for offset in range(count):
        day = window.start + timedelta(days=offset)
        selections.append(
            f"select id, type, actor, repo, created_at from `githubarchive.day.{day:%Y%m%d}`"
        )
    template = (_ROOT / "sql/bigquery/extract_recent_activity.sql").read_text()
    return (
        template.replace("__DAILY_TABLES__", "\n        union all\n        ".join(selections))
        .replace("__START__", window.start.isoformat())
        .replace("__END__", window.end.isoformat())
    )


def normalize_event(row: dict) -> dict:
    """Validate the event contract before accepting a new checkpoint."""
    event = {
        key: str(row[key])
        for key in ("event_id", "event_type", "event_category", "actor_login", "repo_name")
    }
    if any(not value or value == "None" for value in event.values()):
        raise ValueError("Event has a missing identity or scope field.")
    timestamp = row["created_at"]
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        raise ValueError("Event timestamp must include its timezone.")
    event["created_at"] = timestamp.astimezone(UTC).isoformat()
    return event


def merge_events(previous: list[dict], incoming: list[dict], window: Window) -> list[dict]:
    """Upsert stable IDs, include late arrivals, retain at most 90 days."""
    floor = max(window.coverage_start, window.end - timedelta(days=RETAIN_DAYS))
    by_id = {}
    for row in previous:
        event = normalize_event(row)
        day = date.fromisoformat(event["created_at"][:10])
        if floor <= day < window.end:
            by_id[event["event_id"]] = event
    for row in incoming:
        event = normalize_event(row)
        day = date.fromisoformat(event["created_at"][:10])
        if not window.start <= day < window.end:
            raise ValueError("Source returned an event outside the planned UTC range.")
        if day >= floor:
            by_id[event["event_id"]] = event
    return sorted(by_id.values(), key=lambda event: (event["created_at"], event["event_id"]))


def summarize(state: dict, state_sha256: str) -> dict:
    """Aggregate only the recent snapshot; never use historical model tables."""
    events = state["events"]
    days: dict[str, dict] = {}
    for event in events:
        day = event["created_at"][:10]
        bucket = days.setdefault(day, {"events": 0, "contributors": set()})
        bucket["events"] += 1
        bucket["contributors"].add(event["actor_login"])
    start = date.fromisoformat(state["coverage_start"])
    end = date.fromisoformat(state["through_exclusive"])
    daily = []
    for offset in range((end - start).days):
        day = (start + timedelta(days=offset)).isoformat()
        bucket = days.get(day, {"events": 0, "contributors": set()})
        daily.append(
            {
                "date": day,
                "events": bucket["events"],
                "contributors": len(bucket["contributors"]),
            }
        )
    return {
        "schema_version": 1,
        "status": "ready",
        "mode": "manual",
        "source": "GH Archive via BigQuery",
        "coverage_start": start.isoformat(),
        "through_exclusive": end.isoformat(),
        "refreshed_at": state["refreshed_at"],
        "last_event_at": max((e["created_at"] for e in events), default=None),
        "event_count": len(events),
        "active_contributors": len({e["actor_login"] for e in events}),
        "pr_issue_events": sum(e["event_category"] in ("pull_request", "issue") for e in events),
        "daily": daily,
        "query": state["query"],
        "state_sha256": state_sha256,
    }


def encode_state(state: dict) -> bytes:
    """Deterministic encoding makes state checksums and repeat runs stable."""
    raw = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > MAX_STATE_BYTES:
        raise ValueError("State exceeds 64 MiB uncompressed; no files were published.")
    return gzip.compress(raw, mtime=0)


def load_state(directory: Path) -> dict | None:
    """Require summary and durable state to agree before querying anything."""
    summary_path = directory / _SUMMARY_NAME
    state_path = directory / _STATE_NAME
    if not summary_path.exists():
        raise ValueError("Recent activity summary is missing.")
    summary = json.loads(summary_path.read_text())
    if summary.get("status") == "not_initialized" and not state_path.exists():
        return None
    if not state_path.exists():
        raise ValueError("Cursor state is missing; refusing an implicit re-bootstrap.")
    encoded = state_path.read_bytes()
    with gzip.open(state_path, "rb") as stream:
        raw = stream.read(MAX_STATE_BYTES + 1)
    if len(raw) > MAX_STATE_BYTES:
        raise ValueError("State exceeds the supported size.")
    state = json.loads(raw)
    if state["schema_version"] != 1:
        raise ValueError("Unsupported state schema.")
    window = Window(
        date.fromisoformat(state["coverage_start"]),
        date.fromisoformat(state["through_exclusive"]),
        date.fromisoformat(state["coverage_start"]),
        date.fromisoformat(state["through_exclusive"]),
    )
    if not 0 < (window.end - window.start).days <= RETAIN_DAYS:
        raise ValueError("Invalid retained coverage.")
    validated = merge_events([], state["events"], window)
    if validated != state["events"]:
        raise ValueError("Persisted events are duplicated, unordered, or outside coverage.")
    expected = summarize(state, hashlib.sha256(encoded).hexdigest())
    if summary != expected:
        raise ValueError("Summary and durable checkpoint do not match.")
    return state


def save_snapshot(state: dict, directory: Path) -> None:
    """Stage both outputs; the workflow publishes them together in one commit."""
    encoded = encode_state(state)
    summary = summarize(state, hashlib.sha256(encoded).hexdigest())
    outputs = {
        _STATE_NAME: encoded,
        _SUMMARY_NAME: (json.dumps(summary, indent=2) + "\n").encode(),
    }
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        staging = Path(temporary)
        for name, content in outputs.items():
            (staging / name).write_bytes(content)
        load_state(staging)
        for name in outputs:
            os.replace(staging / name, directory / name)


def bounded_bytes(value: str) -> int:
    """Refuse missing/negative caps and unusually large manual scans."""
    number = int(value)
    if not 0 < number <= MAX_BYTES_BILLED:
        raise argparse.ArgumentTypeError("Cap must be 1..20000000000 bytes (20 GB).")
    return number


def refresh(
    *,
    project: str,
    location: str,
    state: dict | None,
    window: Window,
    directory: Path,
    dry_run: bool,
    maximum_bytes_billed: int | None,
) -> dict:
    """Always estimate first; only an explicitly capped apply can query data."""
    if not project:
        raise ValueError("An explicit billing project is required.")
    if not dry_run and (
        maximum_bytes_billed is None or not 0 < maximum_bytes_billed <= MAX_BYTES_BILLED
    ):
        raise ValueError("Apply requires a positive cap of at most 20 GB.")

    # Keep pure checkpoint validation and tests credential-free.
    from google.cloud import bigquery

    sql = render_sql(window)
    with bigquery.Client(project=project, location=location) as client:
        estimate = client.query(
            sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        )
        estimated = estimate.total_bytes_processed
        if estimated is None:
            raise ValueError("BigQuery did not provide an estimate; apply is refused.")
        report = {
            "start": window.start.isoformat(),
            "end_exclusive": window.end.isoformat(),
            "requested_end": window.requested_end.isoformat(),
            "caught_up": window.caught_up,
            "estimated_bytes": estimated,
            "maximum_bytes_billed": maximum_bytes_billed,
            "dry_run": dry_run,
            "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        }
        print(json.dumps(report, indent=2))
        if dry_run:
            return report
        if estimated > maximum_bytes_billed:
            raise ValueError("Estimate exceeds your cap; no data query was executed.")
        job = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                maximum_bytes_billed=maximum_bytes_billed, use_query_cache=True
            ),
        )
        incoming = [dict(row.items()) for row in job.result()]
        events = merge_events(state["events"] if state else [], incoming, window)
        checkpoint = {
            "schema_version": 1,
            "coverage_start": max(
                window.coverage_start, window.end - timedelta(days=RETAIN_DAYS)
            ).isoformat(),
            "through_exclusive": window.end.isoformat(),
            "refreshed_at": datetime.now(UTC).isoformat(),
            "events": events,
            "query": {
                **report,
                "job_id": job.job_id,
                "project": project,
                "bytes_processed": job.total_bytes_processed,
                "bytes_billed": job.total_bytes_billed,
                "run_id": os.environ.get("GITHUB_RUN_ID"),
                "source_commit": os.environ.get("GITHUB_SHA"),
            },
        }
        save_snapshot(checkpoint, directory)
        report["event_count"] = len(events)
        report["bytes_billed"] = job.total_bytes_billed
        return report


def main() -> None:
    """Default to estimate-only; validate-only never authenticates or queries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--location", default="US")
    parser.add_argument("--maximum-bytes-billed", type=bounded_bytes)
    parser.add_argument("--end-date", type=date.fromisoformat)
    args = parser.parse_args()
    try:
        state = load_state(_DATA)
        if args.validate_only:
            print("Recent activity checkpoint valid.")
            return
        now = datetime.now(UTC)
        window = plan_window(state, args.end_date or available_end(now), now)
        if window is None:
            print("Already caught up to the requested end; no BigQuery call.")
            return
        report = refresh(
            project=args.project,
            location=args.location,
            state=state,
            window=window,
            directory=_DATA,
            dry_run=not args.apply,
            maximum_bytes_billed=args.maximum_bytes_billed,
        )
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with Path(summary).open("a") as output:
                output.write("### Recent activity refresh\n\n```json\n")
                output.write(json.dumps(report, indent=2) + "\n```\n")
                output.write(
                    "\nEstimate-only reads no event rows. Apply uses your explicit "
                    "query cap; download/network usage and hosting limits are separate.\n"
                )
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
