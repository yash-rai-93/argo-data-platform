"""Resumable, budgeted 90-day backfill; never publishes production report data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from etl import pilot_activity as pilot
from etl.refresh_activity import bounded_bytes


def configuration(project: str, scope_hash: str, end: date) -> dict:
    return {
        "schema_version": 1,
        "project": project,
        "scope_sha256": scope_hash,
        "batches": pilot.plan(end, datetime.now(UTC), 90),
        "location": "US",
        "query_contract_sha256": hashlib.sha256(
            "\n".join(
                pilot.render_sql(
                    date.fromisoformat(w["start"]), date.fromisoformat(w["end_exclusive"])
                )
                for w in pilot.plan(end, datetime.now(UTC), 90)
            ).encode()
        ).hexdigest(),
    }


def initial_state(config: dict, total_cap: int) -> dict:
    return {
        "config": config,
        "total_cap": total_cap,
        "completed": [],
        "failed": [],
        "pending": None,
    }


def accounted(state: dict) -> int:
    return (
        sum(batch["bytes_billed"] for batch in state["completed"])
        + sum(batch["cap"] for batch in state["failed"])
        + (state["pending"]["cap"] if state["pending"] else 0)
    )


def validate_state(state: dict, config: dict, total_cap: int) -> None:
    if state["config"] != config or state["total_cap"] != total_cap:
        raise ValueError("Backfill config or total cap changed; reuse the pinned settings.")
    batches = config["batches"]
    if len(state["completed"]) > len(batches):
        raise ValueError("Checkpoint contains excess batches.")
    for i, batch in enumerate(state["completed"]):
        if batch["window"] != batches[i] or not 0 <= batch["bytes_billed"] <= batch["cap"]:
            raise ValueError("Completed batches are discontinuous or have invalid billing.")
    pending = state["pending"]
    if pending and (
        len(state["completed"]) == len(batches)
        or pending["window"] != batches[len(state["completed"])]
        or pending["cap"] <= 0
    ):
        raise ValueError("Pending batch does not match the approved cursor.")
    if accounted(state) > total_cap or accounted(state) < 0:
        raise ValueError("Checkpoint exceeds its cumulative query budget.")


class Checkpoints:
    """A GCS compare-and-swap checkpoint, plus immutable validated batch manifests."""

    def __init__(self, bucket, prefix: str):
        self.bucket, self.prefix = bucket, prefix
        self.name = prefix + "/checkpoint.json"

    def read_json(self, name: str):
        from google.api_core.exceptions import NotFound

        blob = self.bucket.blob(name)
        try:
            blob.reload()
            generation = int(blob.generation)
            return json.loads(blob.download_as_bytes(if_generation_match=generation)), generation
        except NotFound:
            return None, 0

    def load(self):
        return self.read_json(self.name)

    def save(self, state: dict, generation: int) -> int:
        blob = self.bucket.blob(self.name)
        blob.upload_from_string(
            pilot.canonical_json(state),
            content_type="application/json",
            if_generation_match=generation,
        )
        return int(blob.generation)

    def immutable(self, name: str, content: bytes) -> None:
        from google.api_core.exceptions import PreconditionFailed

        blob = self.bucket.blob(name)
        try:
            blob.upload_from_string(
                content,
                content_type="application/json",
                if_generation_match=0,
            )
        except PreconditionFailed:
            if blob.download_as_bytes() != content:
                raise ValueError("Immutable manifest content conflicts.") from None


def reserve(state: dict, window: dict, cap: int, estimate: int, prefix: str) -> dict:
    if state["pending"]:
        raise ValueError("Resolve the pending batch before reserving another.")
    if estimate is None or estimate > cap or cap <= 0:
        raise ValueError("Missing estimate or batch estimate exceeds cap.")
    if accounted(state) + cap > state["total_cap"]:
        raise ValueError("Remaining cumulative budget cannot reserve this query cap.")
    attempt = uuid.uuid4().hex
    pending = {
        "window": window,
        "cap": cap,
        "estimated_bytes": estimate,
        "job_id": "argo_backfill_" + attempt,
        "prefix": prefix + "/attempts/" + attempt,
        "reserved_at": datetime.now(UTC).isoformat(),
    }
    state["pending"] = pending
    return pending


def check_manifest(report: dict, pending: dict, scope_hash: str) -> None:
    if (
        report["window"] != pending["window"]
        or report["job_id"] != pending["job_id"]
        or report["scope_sha256"] != scope_hash
        or report["stage"] != "validated"
        or not 0 <= report["bytes_billed"] <= pending["cap"]
        or sum(day["events"] for day in report["quality"]["queried_days"])
        != report["quality"]["event_count"]
        or sum(repo["events"] for repo in report["quality"]["repositories"])
        != report["quality"]["event_count"]
    ):
        raise ValueError("Batch manifest does not reconcile with the reserved query.")


def complete(state: dict, pending: dict, report: dict) -> None:
    check_manifest(report, pending, state["config"]["scope_sha256"])
    state["completed"].append(
        {
            "window": pending["window"],
            "cap": pending["cap"],
            "bytes_billed": report["bytes_billed"],
            "job_id": pending["job_id"],
            "manifest": pending["prefix"] + "/manifest.json",
            "event_count": report["quality"]["event_count"],
        }
    )
    state["pending"] = None


def query_parameters(scope: dict):
    from google.cloud import bigquery

    return [
        bigquery.ArrayQueryParameter(
            "repository_ids", "STRING", [r["repository_id"] for r in scope["repositories"]]
        )
    ]


def estimate_batch(client, scope: dict, window: dict) -> int:
    from google.cloud import bigquery

    sql = pilot.render_sql(
        date.fromisoformat(window["start"]), date.fromisoformat(window["end_exclusive"])
    )
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            query_parameters=query_parameters(scope),
        ),
    )
    if job.total_bytes_processed is None:
        raise ValueError("BigQuery returned no estimate.")
    return job.total_bytes_processed


def get_or_submit(client, scope: dict, pending: dict):
    from google.api_core.exceptions import Conflict, NotFound
    from google.cloud import bigquery

    try:
        return client.get_job(pending["job_id"], location="US")
    except NotFound:
        reserved_at = datetime.fromisoformat(
            pending.get("reserved_at", datetime.now(UTC).isoformat())
        )
        if datetime.now(UTC) - reserved_at > timedelta(days=1):
            raise ValueError(
                "Old pending job is missing; refuse automatic re-submission."
            ) from None
        sql = pilot.render_sql(
            date.fromisoformat(pending["window"]["start"]),
            date.fromisoformat(pending["window"]["end_exclusive"]),
        )
        try:
            return client.query(
                sql,
                job_id=pending["job_id"],
                location="US",
                job_retry=None,
                job_config=bigquery.QueryJobConfig(
                    maximum_bytes_billed=pending["cap"],
                    query_parameters=query_parameters(scope),
                ),
            )
        except Conflict:
            return client.get_job(pending["job_id"], location="US")


def land_batch(
    store: Checkpoints,
    client,
    scope: dict,
    scope_hash: str,
    pending: dict,
    *,
    retry_failed: bool = False,
) -> dict | None:
    manifest_name = pending["prefix"] + "/manifest.json"
    report, _ = store.read_json(manifest_name)
    if report is not None:
        check_manifest(report, pending, scope_hash)
        return report
    job = get_or_submit(client, scope, pending)
    if job.state == "DONE" and job.error_result:
        if retry_failed:
            return None
        raise ValueError(
            "Pinned BigQuery job failed. Inspect it; use retry-failed explicitly to "
            "reserve another attempt. The old attempt remains charged at its full cap."
        )
    rows = job.result()
    with tempfile.TemporaryDirectory() as temporary:
        path, quality = pilot.materialize(
            rows,
            scope,
            date.fromisoformat(pending["window"]["start"]),
            date.fromisoformat(pending["window"]["end_exclusive"]),
            Path(temporary),
        )
        from google.api_core.exceptions import PreconditionFailed

        event_name = pending["prefix"] + "/events.jsonl.gz"
        blob = store.bucket.blob(event_name)
        try:
            blob.upload_from_filename(
                str(path),
                content_type="application/gzip",
                if_generation_match=0,
            )
        except PreconditionFailed:
            # Stream an existing upload to disk before accepting an interrupted attempt.
            existing = Path(temporary) / "existing.gz"
            blob.download_to_filename(str(existing))
            with existing.open("rb") as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != quality["sha256"]:
                    raise ValueError("Existing batch data checksum differs.") from None
        if job.total_bytes_billed is None:
            raise ValueError("Actual billing unavailable; keep the cap reservation.")
        report = {
            "schema_version": 1,
            "stage": "validated",
            "window": pending["window"],
            "scope_sha256": scope_hash,
            "job_id": pending["job_id"],
            "bytes_processed": job.total_bytes_processed,
            "bytes_billed": job.total_bytes_billed,
            "quality": quality,
            "source_commit": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "events_uri": f"gs://{store.bucket.name}/{event_name}",
        }
        check_manifest(report, pending, scope_hash)
        store.immutable(manifest_name, pilot.canonical_json(report))
        return report


def execute(
    store: Checkpoints,
    client,
    scope: dict,
    config: dict,
    *,
    total_cap: int,
    batch_cap: int | None,
    apply: bool = False,
    max_batches: int = 3,
    retry_failed: bool = False,
) -> dict:
    if not 0 < total_cap <= pilot.MAX_BYTES_BILLED:
        raise ValueError("Cumulative budget must be 1..20000000000 bytes.")
    state, generation = store.load()
    if state is None:
        state = initial_state(config, total_cap)
    validate_state(state, config, total_cap)
    if apply and (
        batch_cap is None
        or not 0 < batch_cap <= pilot.MAX_BYTES_BILLED
        or not 1 <= max_batches <= 13
    ):
        raise ValueError("Apply requires a bounded batch cap and 1..13 batches per invocation.")
    if not apply:
        estimates = [
            {**window, "estimated_bytes": estimate_batch(client, scope, window)}
            for window in config["batches"][len(state["completed"]) :]
        ]
        return {
            "stage": "estimate",
            "config": config,
            "remaining_batches": estimates,
            "estimated_remaining_bytes": sum(e["estimated_bytes"] for e in estimates),
            "accounted_bytes": accounted(state),
            "total_cap": total_cap,
            "pending_job": state["pending"]["job_id"] if state["pending"] else None,
        }
    for _ in range(max_batches):
        if len(state["completed"]) == len(config["batches"]):
            break
        pending = state["pending"]
        if not pending:
            window = config["batches"][len(state["completed"])]
            pending = reserve(
                state,
                window,
                batch_cap,
                estimate_batch(client, scope, window),
                store.prefix,
            )
            # CAS reserves the full maximum before a paid query can be submitted.
            generation = store.save(state, generation)
        report = land_batch(
            store, client, scope, config["scope_sha256"], pending, retry_failed=retry_failed
        )
        if report is None:
            state["failed"].append(pending)
            state["pending"] = None
        else:
            complete(state, pending, report)
        generation = store.save(state, generation)
    return {
        "stage": "complete" if len(state["completed"]) == len(config["batches"]) else "in_progress",
        "checkpoint_uri": f"gs://{store.bucket.name}/{store.name}",
        "batches_completed": len(state["completed"]),
        "batches_total": len(config["batches"]),
        "accounted_bytes": accounted(state),
        "total_cap": total_cap,
        "event_count": sum(b["event_count"] for b in state["completed"]),
        "approved_through_exclusive": state["completed"][-1]["window"]["end_exclusive"]
        if state["completed"]
        else config["batches"][0]["start"],
        "production_published": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET"))
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--total-max-bytes-billed", type=bounded_bytes, required=True)
    parser.add_argument("--maximum-bytes-billed", type=bounded_bytes)
    parser.add_argument("--max-batches", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.project or not args.bucket:
        parser.error("Explicit GCP project and private GCS bucket required.")
    try:
        scope, digest = pilot.load_scope()
        config = configuration(args.project, digest, args.end_date)
        key = hashlib.sha256(pilot.canonical_json(config)).hexdigest()
        from google.cloud import bigquery, storage

        with (
            storage.Client(project=args.project) as storage_client,
            bigquery.Client(project=args.project, location="US") as client,
        ):
            store = Checkpoints(storage_client.bucket(args.bucket), "backfills/" + key)
            report = execute(
                store,
                client,
                scope,
                config,
                total_cap=args.total_max_bytes_billed,
                batch_cap=args.maximum_bytes_billed,
                apply=args.apply,
                max_batches=args.max_batches,
                retry_failed=args.retry_failed,
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
