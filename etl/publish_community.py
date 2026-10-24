"""Verify approved backfill data and create a public report snapshot; no BigQuery calls."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from etl import backfill_activity as backfill
from etl import pilot_activity as pilot
from etl import refresh_activity as refresh


def digest_file(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_batch(store, completed, scope, scope_hash):
    """Verify a landed batch against its checkpoint, digest, scope, and metrics."""
    names = {r["repository_id"]: r["name"] for r in scope["repositories"]}
    manifest_name = completed["manifest"]
    pattern = re.escape(store.prefix) + r"/attempts/[a-f0-9]{32}/manifest.json"
    if not re.fullmatch(pattern, manifest_name):
        raise ValueError("Batch manifest escaped the approved backfill.")
    manifest, _ = store.read_json(manifest_name)
    pending = {
        "window": completed["window"],
        "job_id": completed["job_id"],
        "cap": completed["cap"],
    }
    backfill.check_manifest(manifest, pending, scope_hash)
    if manifest["bytes_billed"] != completed["bytes_billed"]:
        raise ValueError("Manifest billing differs from checkpoint.")
    start = date.fromisoformat(completed["window"]["start"])
    end = date.fromisoformat(completed["window"]["end_exclusive"])
    event_name = manifest_name.removesuffix("manifest.json") + "events.jsonl.gz"
    if manifest["events_uri"] != f"gs://{store.bucket.name}/{event_name}":
        raise ValueError("Event object escaped its manifest.")
    with tempfile.TemporaryDirectory() as temporary:
        packed = Path(temporary) / "events.gz"
        store.bucket.blob(event_name).download_to_filename(str(packed))
        if digest_file(packed) != manifest["quality"]["sha256"]:
            raise ValueError("Batch checksum mismatch.")
        with gzip.open(packed, "rb") as source:
            raw = source.read(refresh.MAX_STATE_BYTES + 1)
        if len(raw) > refresh.MAX_STATE_BYTES:
            raise ValueError("Batch exceeds supported size.")
        rows = [
            pilot.validate_row(json.loads(line), names, start, end) for line in raw.splitlines()
        ]
        _, recomputed = pilot.materialize(rows, scope, start, end, Path(temporary))
        for key in ("event_count", "distinct_accounts", "queried_days", "repositories"):
            if recomputed[key] != manifest["quality"][key]:
                raise ValueError("Batch metrics do not reconcile: " + key)
        if recomputed["event_count"] != completed["event_count"]:
            raise ValueError("Checkpoint event count differs.")
    return rows, manifest


def assemble(store, checkpoint, scope, scope_hash, output):
    config = checkpoint["config"]
    backfill.validate_state(checkpoint, config, checkpoint["total_cap"])
    expected = backfill.configuration(
        config["project"], scope_hash, date.fromisoformat(config["batches"][-1]["end_exclusive"])
    )
    if config != expected or checkpoint["pending"] or len(checkpoint["completed"]) != 13:
        raise ValueError("Publication requires a complete, pinned 90-day backfill.")
    by_id, processed, billed, incoming = {}, 0, 0, 0
    names = {r["repository_id"]: r["name"] for r in scope["repositories"]}
    for completed in checkpoint["completed"]:
        rows, manifest = read_batch(store, completed, scope, scope_hash)
        incoming += len(rows)
        for row in rows:
            event = refresh.normalize_event(row)
            old = by_id.get(event["event_id"])
            if old and old != event:
                raise ValueError("Conflicting event ID across batches.")
            by_id[event["event_id"]] = event
        processed += manifest["bytes_processed"]
        billed += manifest["bytes_billed"]
    first, last = config["batches"][0]["start"], config["batches"][-1]["end_exclusive"]
    now = datetime.now(UTC).isoformat()
    events = sorted(by_id.values(), key=lambda row: (row["created_at"], row["event_id"]))
    state = {
        "schema_version": 2,
        "coverage_start": first,
        "through_exclusive": last,
        "covered_days": refresh.dates(first, last),
        "refreshed_at": now,
        "validated_at": now,
        "events": events,
        "query": {
            "kind": "backfill",
            "batches": 13,
            "bytes_processed": processed,
            "bytes_billed": billed,
            "maximum_bytes_billed": checkpoint["total_cap"],
            "accounted_bytes": backfill.accounted(checkpoint),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "source_commit": os.environ.get("GITHUB_SHA"),
        },
    }
    refresh.save_snapshot(state, output)
    state_path = output / "recent-activity-state.json.gz"
    summary_path = output / "recent-activity.json"
    summary = json.loads(summary_path.read_text())
    state["repositories"] = sorted(names.values())
    state_path.write_bytes(refresh.encode_state(state))
    summary["state_sha256"] = digest_file(state_path)
    summary["publication"] = {
        "kind": "backfill",
        "batches": 13,
        "selected_repositories": len(names),
        "observed_repositories": len({e["repo_name"] for e in events}),
        "source_rows": incoming,
        "cross_batch_duplicate_ids": incoming - len(events),
        "checksums_verified": 13,
    }
    summary["quality"]["last_query"] = None
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    audit = {
        "event_count": len(events),
        "distinct_accounts": len({e["actor_login"] for e in events}),
        "coverage_start": first,
        "through_exclusive": last,
        "covered_days": 90,
        "scope_sha256": scope_hash,
        "summary_sha256": digest_file(summary_path),
        "state_sha256": digest_file(state_path),
        "publication": summary["publication"],
        "query": state["query"],
    }
    (output / "publication-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    parser.add_argument("--bucket", default=os.environ.get("GCS_BUCKET"))
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/generated/community"))
    args = parser.parse_args()
    if not args.project or not args.bucket:
        parser.error("Project and private source bucket required.")
    scope, scope_hash = pilot.load_scope()
    config = backfill.configuration(args.project, scope_hash, args.end_date)
    key = hashlib.sha256(pilot.canonical_json(config)).hexdigest()
    from google.cloud import storage

    with storage.Client(project=args.project) as client:
        store = backfill.Checkpoints(client.bucket(args.bucket), "backfills/" + key)
        checkpoint, _ = store.load()
        if checkpoint is None:
            parser.error("Approved backfill checkpoint missing.")
        audit = assemble(store, checkpoint, scope, scope_hash, args.output)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
