"""Estimate or land an isolated seven-day, 500-repository pilot in GCS.

This does not advance the live report cursor, publish a dashboard, or retrain models.
Cloud execution reuses ADC / GitHub Workload Identity Federation.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from etl.refresh_activity import MAX_BYTES_BILLED, available_end, bounded_bytes, normalize_event

ROOT = Path(__file__).resolve().parents[1]
SCOPE_PATH = ROOT / "config/repository-scope-v1.json"
EVENT_TYPES = (
    "PushEvent",
    "PullRequestEvent",
    "PullRequestReviewEvent",
    "PullRequestReviewCommentEvent",
    "IssuesEvent",
    "IssueCommentEvent",
    "CommitCommentEvent",
    "CreateEvent",
    "ForkEvent",
    "WatchEvent",
    "ReleaseEvent",
)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def load_scope(path: Path = SCOPE_PATH) -> tuple[dict, str]:
    scope = json.loads(path.read_text(encoding="utf-8"))
    repos = scope["repositories"]
    if scope["schema_version"] != 1 or scope["target_repositories"] != 500 or len(repos) != 500:
        raise ValueError("Pilot requires exactly 500 versioned repositories.")
    ids, names = set(), set()
    for repo in repos:
        identifier, name = repo["repository_id"], repo["name"]
        if not isinstance(identifier, str) or not re.fullmatch(r"[1-9][0-9]*", identifier):
            raise ValueError("Repository IDs must be positive decimal strings.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            raise ValueError("Invalid repository name.")
        if identifier in ids or name.lower() in names:
            raise ValueError("Repository IDs and canonical names must be unique.")
        ids.add(identifier)
        names.add(name.lower())
    return scope, hashlib.sha256(canonical_json(scope)).hexdigest()


def plan(end: date, now: datetime, days: int = 7) -> list[dict]:
    if end > available_end(now) or not 1 <= days <= 90:
        raise ValueError("Use 1..90 complete days, leaving yesterday and today unqueried.")
    start = end - timedelta(days=days)
    batches = []
    while start < end:
        stop = min(end, start + timedelta(days=7))
        batches.append({"start": start.isoformat(), "end_exclusive": stop.isoformat()})
        start = stop
    return batches


def render_sql(start: date, end: date) -> str:
    if not 1 <= (end - start).days <= 7:
        raise ValueError("Each pilot query must cover 1..7 daily tables.")
    tables = [
        "SELECT id, type, actor, repo, created_at FROM "
        f"`githubarchive.day.{start + timedelta(days=i):%Y%m%d}`"
        for i in range((end - start).days)
    ]
    # Use the approved event categories and account exclusions from the existing
    # extraction contract. Only the scope changes from names to stable repo IDs.
    template = (ROOT / "sql/bigquery/extract_recent_activity.sql").read_text(encoding="utf-8")
    scoped = template[template.index("scoped as (") :]
    scoped = scoped.replace(
        "repo.name as repo_name,",
        "repo.name as repo_name,\n        cast(repo.id as string) as repository_id,",
    )
    scoped = scoped.replace("s.event_id,", "s.event_id,\n    s.repository_id,", 1)
    scoped = scoped.replace(
        "inner join python_repos as p\n    on s.repo_name = p.repo",
        "where s.repository_id in unnest(@repository_ids)",
    )
    scoped = scoped.replace("where s.actor_login not like", "and s.actor_login not like")
    return (
        ("with " + scoped)
        .replace("__DAILY_TABLES__", "\nunion all\n".join(tables))
        .replace("__START__", start.isoformat())
        .replace("__END__", end.isoformat())
    )


def validate_row(row: dict, names: dict[str, str], start: date, end: date) -> dict:
    identifier = str(row["repository_id"])
    if identifier not in names:
        raise ValueError("Event repository is outside the selected scope.")
    event = normalize_event(row)
    if event["event_type"] not in EVENT_TYPES:
        raise ValueError("Unexpected source event type.")
    if not start <= date.fromisoformat(event["created_at"][:10]) < end:
        raise ValueError("Event is outside the requested UTC range.")
    expected = category(event["event_type"])
    if event["event_category"] != expected:
        raise ValueError("Event category differs from the approved contract.")
    event["repository_id"] = identifier
    event["source_repo_name"] = event["repo_name"]
    event["repo_name"] = names[identifier]
    return event


def category(event_type: str) -> str:
    # Validation of the existing SQL contract, not a second serving definition.
    if event_type == "PushEvent":
        return "commit"
    if event_type.startswith("PullRequest"):
        return "pull_request"
    if event_type.startswith("Issue"):
        return "issue"
    if event_type == "CommitCommentEvent":
        return "comment"
    if event_type in ("ForkEvent", "WatchEvent"):
        return "engagement"
    return "release"


def materialize(rows, scope: dict, start: date, end: date, directory: Path) -> tuple[Path, dict]:
    """Use disk-backed deduplication; never hold the event extract in memory."""
    names = {repo["repository_id"]: repo["name"] for repo in scope["repositories"]}
    database = sqlite3.connect(directory / "events.sqlite")
    duplicates = 0
    try:
        database.execute(
            "create table events "
            "(id text primary key, day text, actor text, repo text, payload text)"
        )
        for row in rows:
            event = validate_row(dict(row.items()), names, start, end)
            payload = canonical_json(event).decode().strip()
            old = database.execute(
                "select payload from events where id = ?", (event["event_id"],)
            ).fetchone()
            if old:
                if old[0] != payload:
                    raise ValueError("Conflicting records share an event ID.")
                duplicates += 1
                continue
            database.execute(
                "insert into events values (?, ?, ?, ?, ?)",
                (
                    event["event_id"],
                    event["created_at"][:10],
                    event["actor_login"],
                    event["repository_id"],
                    payload,
                ),
            )
        database.commit()
        count, accounts = database.execute(
            "select count(*), count(distinct actor) from events"
        ).fetchone()
        daily = dict(database.execute("select day, count(*) from events group by day"))
        observed = dict(database.execute("select repo, count(*) from events group by repo"))
        output = directory / "events.jsonl.gz"
        with (
            output.open("wb") as raw,
            gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed,
        ):
            for (payload,) in database.execute("select payload from events order by day, id"):
                compressed.write((payload + "\n").encode())
        with output.open("rb") as checksum_input:
            digest = hashlib.file_digest(checksum_input, "sha256").hexdigest()
        return output, {
            "event_count": count,
            "distinct_accounts": accounts,
            "duplicate_source_rows": duplicates,
            "sha256": digest,
            "queried_days": [
                {
                    "date": (start + timedelta(days=i)).isoformat(),
                    "events": daily.get((start + timedelta(days=i)).isoformat(), 0),
                }
                for i in range((end - start).days)
            ],
            "repositories": [
                {"repository_id": identifier, "name": name, "events": observed.get(identifier, 0)}
                for identifier, name in names.items()
            ],
        }
    finally:
        database.close()


def upload_immutable(bucket, name: str, content: bytes) -> None:
    bucket.blob(name).upload_from_string(
        content, content_type="application/json", if_generation_match=0
    )


def run(
    *,
    project: str,
    scope: dict,
    scope_hash: str,
    start: date,
    end: date,
    dry_run: bool = True,
    cap: int | None = None,
    bucket_name: str | None = None,
    location: str = "US",
) -> dict:
    if not project or location != "US":
        raise ValueError("Explicit project and US BigQuery location are required.")
    if not dry_run and (cap is None or not 0 < cap <= MAX_BYTES_BILLED or not bucket_name):
        raise ValueError("Apply requires a GCS bucket and explicit cap of at most 20 GB.")
    sql = render_sql(start, end)
    from google.cloud import bigquery

    parameters = [
        bigquery.ArrayQueryParameter(
            "repository_ids", "STRING", [repo["repository_id"] for repo in scope["repositories"]]
        )
    ]
    with bigquery.Client(project=project, location=location) as client:
        estimate = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
                query_parameters=parameters,
            ),
        )
        estimated = estimate.total_bytes_processed
        if estimated is None:
            raise ValueError("Missing query estimate; execution refused.")
        report = {
            "schema_version": 1,
            "stage": "estimate",
            "dry_run": dry_run,
            "project": project,
            "location": location,
            "scope_sha256": scope_hash,
            "repositories_selected": 500,
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "estimated_bytes": estimated,
            "maximum_bytes_billed": cap,
            "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            "source": "GH Archive via BigQuery",
            "source_completeness": "not guaranteed",
            "source_commit": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
        }
        if dry_run:
            return report
        if estimated > cap:
            raise ValueError("Estimate exceeds cap; no data query executed.")
        from google.cloud import storage

        with storage.Client(project=project) as storage_client:
            bucket = storage_client.bucket(bucket_name)
            attempt = uuid.uuid4().hex
            prefix = f"pilots/{scope_hash}/{start.isoformat()}_{end.isoformat()}/{attempt}"
            # Fail storage permission/configuration checks before the paid query.
            upload_immutable(bucket, prefix + "/started.json", canonical_json(report))
            job = client.query(
                sql,
                job_config=bigquery.QueryJobConfig(
                    maximum_bytes_billed=cap,
                    query_parameters=parameters,
                ),
            )
            with tempfile.TemporaryDirectory() as temporary:
                output, quality = materialize(job.result(), scope, start, end, Path(temporary))
                bucket.blob(prefix + "/events.jsonl.gz").upload_from_filename(
                    str(output),
                    content_type="application/gzip",
                    if_generation_match=0,
                )
                upload_immutable(bucket, prefix + "/scope.json", canonical_json(scope))
                report.update(
                    stage="validated",
                    query_job_id=job.job_id,
                    bytes_processed=job.total_bytes_processed,
                    bytes_billed=job.total_bytes_billed,
                    validated_at=datetime.now(UTC).isoformat(),
                    quality=quality,
                    events_uri=f"gs://{bucket_name}/{prefix}/events.jsonl.gz",
                )
                # Manifest is the commit marker. Incomplete attempts have none.
                upload_immutable(bucket, prefix + "/manifest.json", canonical_json(report))
                report["manifest_uri"] = f"gs://{bucket_name}/{prefix}/manifest.json"
                return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET"))
    parser.add_argument("--maximum-bytes-billed", type=bounded_bytes)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        scope, digest = load_scope()
        batches = plan(args.end_date, datetime.now(UTC), args.days)
        if args.plan_only:
            if args.apply:
                raise ValueError("Plan-only cannot be combined with apply.")
            report = {"scope_sha256": digest, "repositories_selected": 500, "batches": batches}
        else:
            if len(batches) != 1:
                raise ValueError("Execute one 1..7-day pilot batch; use --plan-only for 90 days.")
            report = run(
                project=args.project,
                scope=scope,
                scope_hash=digest,
                start=date.fromisoformat(batches[0]["start"]),
                end=args.end_date,
                dry_run=not args.apply,
                cap=args.maximum_bytes_billed,
                bucket_name=args.bucket,
            )
        encoded = json.dumps(report, indent=2) + "\n"
        print(encoded)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(encoded, encoding="utf-8")
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
