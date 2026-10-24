"""Real Kafka/PySpark recovery test with explicitly synthetic events."""

import json
import tempfile
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
spark = session()
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
            query = start(
                spark, bootstrap, topic, checkpoint, sink, scope, callback=fail_after_commit
            )
            query.awaitTermination()
        except Exception as error:
            if "Synthetic crash after sink commit" not in str(error):
                raise
            failed = True
        assert failed, "Failure injection must execute"
        start(spark, bootstrap, topic, checkpoint, sink, scope).awaitTermination()

        def counts():
            with sink.connect() as db:
                return (
                    db.execute("select count(*) from events").fetchone()[0],
                    db.execute("select count(*) from quarantine").fetchone()[0],
                    db.execute("select count(*) from messages").fetchone()[0],
                )

        assert counts() == (3, 2, 6), counts()
        before = counts()
        start(spark, bootstrap, topic, checkpoint, sink, scope).awaitTermination()
        assert counts() == before, "Restart without input must not add rows"
        publish(spark, records, bootstrap, topic)
        start(spark, bootstrap, topic, checkpoint, sink, scope).awaitTermination()
        assert counts() == (3, 4, 12), counts()
        print(
            json.dumps(
                {
                    "mode": "synthetic_historical_replay",
                    "events": 3,
                    "quarantined_records": 4,
                    "messages": 12,
                    "crash_recovery": "pass",
                    "checkpoint_restart": "pass",
                    "duplicate_replay": "pass",
                    "late_historical_event": "retained",
                }
            ),
            flush=True,
        )
finally:
    spark.stop()
