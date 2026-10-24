"""Real Kafka/PySpark recovery test with explicitly synthetic events."""

import json
import os
import platform
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from etl import pilot_activity as pilot
from streaming.contract import Sink, envelope
from streaming.spark_replay import bind, publish, session, start

scope, scope_hash = pilot.load_scope()
repo = scope["repositories"][0]
coverage = {"coverage_start": "2026-07-25", "through_exclusive": "2026-10-23"}
records = []
for identifier, day in (("one", "2026-10-22"), ("two", "2026-10-21"), ("late", "2026-07-25")):
    event = {
        "event_id": identifier,
        "created_at": day + "T00:00:00+00:00",
        "event_type": "PushEvent",
        "event_category": "commit",
        "repo_name": repo["name"],
        "actor_login": "synthetic-account",
    }
    message = envelope(
        event,
        repo["repository_id"],
        coverage,
        "a" * 64,
        "synthetic-ci",
        datetime.now(UTC).isoformat(),
    )
    records.append((identifier, json.dumps(message)))
records += [records[0], ("bad", "malformed json")]
invalid = json.loads(records[0][1])
invalid["event"]["created_at"] = "invalid timestamp"
records.append(("one", json.dumps(invalid)))
bootstrap, topic = "localhost:19092", "argo.github.replay.v1"
began = time.perf_counter()
evidence = {
    "schema_version": 1,
    "status": "failed",
    "mode": "synthetic_historical_replay",
    "run_id": os.environ.get("GITHUB_RUN_ID"),
    "source_commit": os.environ.get("GITHUB_SHA"),
    "environment": {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "spark": "3.5.6",
        "kafka": "4.2.1",
        "spark_master": "local[2]",
        "topic_partitions": 2,
        "broker_count": 1,
        "sink": "single-driver SQLite",
    },
    "operations": [],
    "trials": [],
    "cost": {
        "gcp_resources_used_by_test": False,
        "gcp_actual_cost_inr": None,
        "github_actions_billed_cost": None,
        "note": "No GCP resources used; CI account billing and deployment costs unverified.",
    },
    "limits": [
        "Three small synthetic trials on a shared CI runner, after warmup.",
        "Consume rate includes query startup; excludes producer and JVM startup.",
        "Replay publication-to-last-commit delay includes intentional producer/broker waiting.",
        "Historical event age is not live source lag; no live source lag measured.",
        "Injected task failure is not VM crash, broker failover, or high-availability evidence.",
    ],
}
spark = session()
evidence["spark_initialization_seconds"] = round(time.perf_counter() - began, 6)


def consume(label, callback=None):
    started = time.perf_counter()
    outcome = "failed"
    try:
        query = start(spark, bootstrap, topic, checkpoint, sink, scope, callback=callback)
        query.awaitTermination()
        outcome = "pass"
        return query
    finally:
        evidence["operations"].append(
            {
                "name": label,
                "outcome": outcome,
                "seconds": round(time.perf_counter() - started, 6),
            }
        )


spark.sparkContext.setLogLevel("WARN")
try:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        checkpoint, database = root / "checkpoint", root / "sink.sqlite"
        contract = bind(checkpoint, database, bootstrap, topic, scope_hash)
        sink = Sink(database, contract)
        publish(spark, records, bootstrap, topic)

        def fail_after_commit(batch_id):
            raise RuntimeError("Synthetic crash after sink commit, before Spark checkpoint commit")

        failed = False
        try:
            consume("injected_failure_after_sink_commit", fail_after_commit)
        except Exception as error:
            if "Synthetic crash after sink commit" not in str(error):
                raise
            failed = True
        assert failed, "Failure injection must execute"
        consume("recovery_from_checkpoint")

        def counts():
            with sink.connect() as db:
                return (
                    db.execute("select count(*) from events").fetchone()[0],
                    db.execute("select count(*) from quarantine").fetchone()[0],
                    db.execute("select count(*) from messages").fetchone()[0],
                )

        assert counts() == (3, 2, 6), counts()
        before = counts()
        consume("restart_without_input")
        assert counts() == before, "Restart without input must not add rows"
        publish(spark, records, bootstrap, topic)
        consume("duplicate_replay")
        assert counts() == (3, 4, 12), counts()
        evidence["recovery_checks"] = {
            "injected_failures": 1,
            "recovered_unique_events": 3,
            "quarantined_records": 4,
            "consumed_messages": 12,
            "checkpoint_restart": "pass",
            "duplicate_replay": "pass",
            "late_historical_event": "retained",
        }
        for trial in range(3):
            published_at = datetime.now(UTC).isoformat()
            origin = time.perf_counter()
            sample = []
            for number in range(1000):
                event = {
                    "event_id": f"benchmark-{trial}-{number}",
                    "created_at": "2026-10-22T00:00:00+00:00",
                    "event_type": "PushEvent",
                    "event_category": "commit",
                    "repo_name": repo["name"],
                    "actor_login": f"synthetic-{number % 50}",
                }
                message = envelope(
                    event,
                    repo["repository_id"],
                    coverage,
                    "a" * 64,
                    f"synthetic-benchmark-{trial}",
                    published_at,
                )
                sample.append((event["event_id"], json.dumps(message)))
            before = counts()
            produced = time.perf_counter()
            publish(spark, sample, bootstrap, topic)
            produce_seconds = time.perf_counter() - produced
            commits = []

            def record_commit(batch_id, committed=commits):
                committed.append(time.perf_counter())

            query = consume(f"benchmark-{trial}", record_commit)
            elapsed = evidence["operations"][-1]["seconds"]
            after = counts()
            assert after == (before[0] + 1000, before[1], before[2] + 1000), after
            assert commits, "Benchmark must reach a sink commit"
            evidence["trials"].append(
                {
                    "trial": trial + 1,
                    "records": 1000,
                    "key_value_bytes": sum(len(k.encode()) + len(v.encode()) for k, v in sample),
                    "producer_seconds": round(produce_seconds, 6),
                    "consumer_seconds": elapsed,
                    "records_per_second": round(1000 / elapsed, 3),
                    "publication_to_last_sink_commit_seconds": round(commits[-1] - origin, 6),
                    "spark_input_rows": sum(p["numInputRows"] for p in query.recentProgress),
                }
            )
        rates = [t["records_per_second"] for t in evidence["trials"]]
        evidence["throughput_records_per_second"] = {
            "minimum": min(rates),
            "median": statistics.median(rates),
            "maximum": max(rates),
        }
        evidence["status"] = "pass"
        evidence["final_counts"] = dict(
            zip(("events", "quarantine", "messages"), counts(), strict=True)
        )

finally:
    evidence["total_seconds"] = round(time.perf_counter() - began, 6)
    output = Path("data/generated/streaming/operational-evidence.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("OPERATIONAL_EVIDENCE=" + json.dumps(evidence), flush=True)
    spark.stop()
