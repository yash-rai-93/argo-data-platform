"""Advance the approved 500-repository report using bounded, resumable daily queries.

The pointer on main is the approved cursor. GCS stores query reservations and
immutable extracts; producing a candidate never advances that approved cursor.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

from etl import backfill_activity as backfill
from etl import pilot_activity as pilot
from etl import publish_community as publish
from etl import refresh_activity as refresh

RELEASE_BASE = "https://github.com/yash-rai-93/argo-data-platform/releases/download/"
DEFAULT_POINTER = pilot.ROOT / "data/community-source.json"


def download(url: str) -> bytes:
    with urlopen(url, timeout=30) as response:
        data = response.read(refresh.MAX_STATE_BYTES + 1)
    if len(data) > refresh.MAX_STATE_BYTES:
        raise ValueError("Release asset exceeds supported size.")
    return data


def load_approved(pointer: dict, scope: dict, fetch=download) -> tuple[dict, str]:
    """Read pinned release assets, then recompute all serving aggregates."""
    summary_url, state_url = pointer["summary_url"], pointer["state_url"]
    match = re.fullmatch(
        re.escape(RELEASE_BASE) + r"(community-data-[0-9]+-[0-9]+)/recent-activity.json",
        summary_url,
    )
    if (
        pointer["schema_version"] != 1
        or not match
        or state_url != RELEASE_BASE + match[1] + "/recent-activity-state.json.gz"
    ):
        raise ValueError("Pointer must pin assets from the same approved community release.")
    summary_raw = fetch(summary_url)
    if hashlib.sha256(summary_raw).hexdigest() != pointer["summary_sha256"]:
        raise ValueError("Approved summary checksum mismatch.")
    summary = json.loads(summary_raw)
    packed = fetch(state_url)
    digest = hashlib.sha256(packed).hexdigest()
    if digest != summary["state_sha256"]:
        raise ValueError("Approved state checksum mismatch.")
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as source:
        raw = source.read(refresh.MAX_STATE_BYTES + 1)
    if len(raw) > refresh.MAX_STATE_BYTES:
        raise ValueError("Approved state exceeds supported size.")
    state = json.loads(raw)
    names = sorted(r["name"] for r in scope["repositories"])
    if state["schema_version"] != 2 or state.get("repositories") != names:
        raise ValueError("Approved snapshot must use the pinned 500-repository registry.")
    first = date.fromisoformat(state["coverage_start"])
    last = date.fromisoformat(state["through_exclusive"])
    if (last - first).days != refresh.RETAIN_DAYS:
        raise ValueError("Approved community snapshot must contain 90 covered days.")
    window = refresh.Window(first, last, first, last)
    if (
        state["covered_days"] != refresh.dates(first.isoformat(), last.isoformat())
        or refresh.merge_events([], state["events"], window) != state["events"]
    ):
        raise ValueError("Approved events or coverage are invalid.")
    for event in state["events"]:
        if (
            event["repo_name"] not in names
            or event["event_type"] not in pilot.EVENT_TYPES
            or event["event_category"] != pilot.category(event["event_type"])
        ):
            raise ValueError("Approved event differs from the scope or category contract.")
    expected = refresh.summarize(state, digest)
    if any(summary.get(key) != value for key, value in expected.items()):
        raise ValueError("Approved aggregates do not reconcile with state.")
    return state, digest


def validate_promotion(approved_pointer, candidate_pointer, scope, fetch=download):
    """Reject stale incremental candidates when their data PR is reviewed."""
    previous, previous_hash = load_approved(approved_pointer, scope, fetch)
    candidate, _ = load_approved(candidate_pointer, scope, fetch)
    if candidate["through_exclusive"] < previous["through_exclusive"]:
        raise ValueError("Candidate would roll back the approved report.")
    if candidate["query"].get("kind") == "incremental" and (
        candidate["query"]["base_state_sha256"] != previous_hash
        or candidate["through_exclusive"] <= previous["through_exclusive"]
    ):
        raise ValueError("Stale incremental candidate; rebuild from the current approved pointer.")
    return candidate["through_exclusive"]


def configuration(project, scope_hash, state, state_hash, requested_end, now):
    """Include two overlap days and advance at most five new days per query."""
    cursor = date.fromisoformat(state["through_exclusive"])
    if not project or requested_end > refresh.available_end(now) or requested_end < cursor:
        raise ValueError("Use a project and an end at/after the cursor, leaving UTC source lag.")
    if requested_end == cursor:
        return None
    start = cursor - timedelta(days=refresh.OVERLAP_DAYS)
    end = min(requested_end, start + timedelta(days=7))
    window = {"start": start.isoformat(), "end_exclusive": end.isoformat()}
    return {
        "schema_version": 1,
        "project": project,
        "location": "US",
        "scope_sha256": scope_hash,
        "base_state_sha256": state_hash,
        "batches": [window],
        "query_contract_sha256": hashlib.sha256(pilot.render_sql(start, end).encode()).hexdigest(),
    }


def merge_snapshot(previous, rows, quality, config, manifest, checkpoint):
    """Retain overlap events, accept late additions, and reject conflicting IDs."""
    window = config["batches"][0]
    start, end = window["start"], window["end_exclusive"]
    floor = (date.fromisoformat(end) - timedelta(days=refresh.RETAIN_DAYS)).isoformat()
    by_id = {e["event_id"]: e for e in previous["events"]}
    incoming = {}
    for row in rows:
        event = refresh.normalize_event(row)
        identifier = event["event_id"]
        old = incoming.get(identifier) or by_id.get(identifier)
        if old is not None and old != event:
            raise ValueError("Conflicting event ID; no candidate can be published.")
        if not start <= event["created_at"][:10] < end:
            raise ValueError("Incoming event outside the reserved query.")
        incoming[identifier] = event
    expired = sum(e["created_at"][:10] < floor for e in by_id.values())
    overlap = len(incoming.keys() & by_id.keys())
    new_ids = len(incoming.keys() - by_id.keys())
    by_id.update(incoming)
    events = sorted(
        (e for e in by_id.values() if floor <= e["created_at"][:10] < end),
        key=lambda e: (e["created_at"], e["event_id"]),
    )
    if len(events) != len(previous["events"]) - expired + new_ids:
        raise ValueError("Retained event reconciliation failed.")
    covered = refresh.dates(floor, end)
    if not set(covered).issubset(set(previous["covered_days"]) | set(refresh.dates(start, end))):
        raise ValueError("Incremental refresh would create a coverage gap.")
    now = datetime.now(UTC).isoformat()
    return {
        "schema_version": 2,
        "coverage_start": floor,
        "through_exclusive": end,
        "covered_days": covered,
        "refreshed_at": now,
        "validated_at": now,
        "repositories": previous["repositories"],
        "scope_sha256": config["scope_sha256"],
        "events": events,
        "quality_run": {
            "incoming_rows": len(rows) + quality["duplicate_source_rows"],
            "duplicate_incoming_ids": quality["duplicate_source_rows"],
            "overlap_ids": overlap,
            "new_ids": new_ids,
            "expired_ids": expired,
            "previous_events": len(previous["events"]),
            "retained_events": len(events),
            "queried_days": len(refresh.dates(start, end)),
            "legacy_coverage_inherited": False,
        },
        "query": {
            "kind": "incremental",
            "batches": 1,
            "start": start,
            "end_exclusive": end,
            "job_id": manifest["job_id"],
            "project": config["project"],
            "bytes_processed": manifest["bytes_processed"],
            "bytes_billed": manifest["bytes_billed"],
            "maximum_bytes_billed": checkpoint["completed"][0]["cap"],
            "accounted_bytes": backfill.accounted(checkpoint),
            "total_max_bytes_billed": checkpoint["total_cap"],
            "base_state_sha256": config["base_state_sha256"],
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "source_commit": os.environ.get("GITHUB_SHA"),
        },
    }


def assemble(store, checkpoint, previous, config, scope, output):
    backfill.validate_state(checkpoint, config, checkpoint["total_cap"])
    if checkpoint["pending"] or len(checkpoint["completed"]) != 1:
        raise ValueError("Incremental query is not complete.")
    rows, manifest = publish.read_batch(
        store, checkpoint["completed"][0], scope, config["scope_sha256"]
    )
    state = merge_snapshot(previous, rows, manifest["quality"], config, manifest, checkpoint)
    refresh.save_snapshot(state, output)
    audit = {
        "kind": "incremental",
        "base_state_sha256": config["base_state_sha256"],
        "scope_sha256": config["scope_sha256"],
        "event_count": len(state["events"]),
        "distinct_accounts": len({e["actor_login"] for e in state["events"]}),
        "coverage_start": state["coverage_start"],
        "through_exclusive": state["through_exclusive"],
        "covered_days": len(state["covered_days"]),
        "checksums_verified": 1,
        "selected_repositories": len(state["repositories"]),
        "quality_run": state["quality_run"],
        "query": state["query"],
        "summary_sha256": publish.digest_file(output / "recent-activity.json"),
        "state_sha256": publish.digest_file(output / "recent-activity-state.json.gz"),
    }
    (output / "publication-audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET"))
    parser.add_argument("--pointer", type=Path, default=DEFAULT_POINTER)
    parser.add_argument(
        "--validate-promotion", type=Path, help="Current main pointer; no cloud calls."
    )
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--maximum-bytes-billed", type=refresh.bounded_bytes)
    parser.add_argument("--total-max-bytes-billed", type=refresh.bounded_bytes)
    parser.add_argument("--output", type=Path, default=Path("data/generated/community"))
    parser.add_argument("--report", type=Path, default=Path("data/generated/community-run.json"))
    args = parser.parse_args()
    if args.validate_promotion:
        scope, _ = pilot.load_scope()
        end = validate_promotion(
            json.loads(args.validate_promotion.read_text(encoding="utf-8")),
            json.loads(args.pointer.read_text(encoding="utf-8")),
            scope,
        )
        print("Candidate promotion verified through exclusive UTC end: " + end)
        return
    if not args.project or not args.bucket or args.total_max_bytes_billed is None:
        parser.error("Explicit project, private GCS bucket, and total query cap required.")
    scope, scope_hash = pilot.load_scope()
    state, digest = load_approved(json.loads(args.pointer.read_text(encoding="utf-8")), scope)
    now = datetime.now(UTC)
    requested = args.end_date or refresh.available_end(now)
    config = configuration(args.project, scope_hash, state, digest, requested, now)
    if config is None:
        report = {"stage": "no_op", "approved_through_exclusive": state["through_exclusive"]}
    else:
        key = hashlib.sha256(pilot.canonical_json(config)).hexdigest()
        from google.cloud import bigquery, storage

        with (
            storage.Client(project=args.project) as storage_client,
            bigquery.Client(project=args.project, location="US") as client,
        ):
            store = backfill.Checkpoints(storage_client.bucket(args.bucket), "incremental/" + key)
            report = backfill.execute(
                store,
                client,
                scope,
                config,
                total_cap=args.total_max_bytes_billed,
                batch_cap=args.maximum_bytes_billed,
                apply=args.apply,
                max_batches=1,
                retry_failed=args.retry_failed,
            )
            if args.apply and report["stage"] == "complete":
                checkpoint, _ = store.load()
                report["audit"] = assemble(store, checkpoint, state, config, scope, args.output)
        report.update(
            base_state_sha256=digest,
            requested_end=requested.isoformat(),
            planned_end_exclusive=config["batches"][0]["end_exclusive"],
            caught_up=config["batches"][0]["end_exclusive"] == requested.isoformat(),
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
