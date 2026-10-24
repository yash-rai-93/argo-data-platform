"""Bounded historical replay through Kafka and PySpark; never updates the live report."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from etl import incremental_community as incremental
from etl import pilot_activity as pilot
from streaming.contract import Sink, envelope

SPARK_VERSION = "4.1.0"
CONNECTOR = "org.apache.spark:spark-sql-kafka-0-10_2.13:" + SPARK_VERSION


def session():
    import pyspark
    from pyspark.sql import SparkSession

    if pyspark.__version__ != SPARK_VERSION:
        raise ValueError("Use the pinned PySpark version " + SPARK_VERSION)
    return (
        SparkSession.builder.master("local[2]")
        .appName("argo-historical-replay")
        .config("spark.jars.packages", CONNECTOR)
        .config("spark.jars.repositories", "https://repo.maven.apache.org/maven2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )


def publish(spark, records, bootstrap, topic):
    """Kafka writes are at least once; the stable event key supports sink dedup."""
    frame = spark.createDataFrame(records, "key string, value string")
    frame.write.format("kafka").option("kafka.bootstrap.servers", bootstrap).option(
        "topic", topic
    ).option("kafka.acks", "all").save()


def bind(checkpoint, database, bootstrap, topic, scope_hash):
    checkpoint, database = Path(checkpoint).resolve(), Path(database).resolve()
    guard = checkpoint / "argo-contract.json"
    contract = {
        "schema_version": 1,
        "topic": topic,
        "bootstrap": bootstrap,
        "scope_sha256": scope_hash,
        "checkpoint": str(checkpoint),
        "database": str(database),
        "spark_version": SPARK_VERSION,
    }
    if guard.exists():
        if json.loads(guard.read_text()) != contract or not database.exists():
            raise ValueError("Checkpoint contract changed or its durable sink is missing.")
    else:
        if database.exists() or (checkpoint.exists() and any(checkpoint.iterdir())):
            raise ValueError("Missing checkpoint binding; refusing offset/sink reset.")
        checkpoint.mkdir(parents=True, exist_ok=True)
        guard.write_bytes(pilot.canonical_json(contract))
    return contract


def start(spark, bootstrap, topic, checkpoint, sink, scope, max_offsets=1000, callback=None):
    from pyspark.sql import functions as f

    schema = (
        "schema_version INT, mode STRING, replay_id STRING, source_state_sha256 STRING, "
        "coverage_start STRING, through_exclusive STRING, published_at STRING, "
        "event STRUCT<event_id:STRING,repository_id:STRING,repo_name:STRING,"
        "event_type:STRING,event_category:STRING,actor_login:STRING,created_at:STRING>"
    )
    source = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "true")
        .option("maxOffsetsPerTrigger", max_offsets)
        .load()
    )
    parsed = source.select(
        "topic",
        "partition",
        "offset",
        f.col("key").cast("string").alias("key"),
        f.col("value").cast("string").alias("value"),
        f.from_json(f.col("value").cast("string"), schema).alias("parsed"),
    ).select(
        "topic",
        "partition",
        "offset",
        "key",
        "value",
        f.to_date(f.try_to_timestamp("parsed.event.created_at")).cast("string").alias("event_day"),
    )

    def commit(batch, batch_id):
        receipt = sink.write(batch_id, (row.asDict() for row in batch.toLocalIterator()), scope)
        print(json.dumps(receipt, sort_keys=True), flush=True)
        if callback:
            callback(batch_id)

    return (
        parsed.writeStream.foreachBatch(commit)
        .option("checkpointLocation", str(checkpoint))
        .trigger(availableNow=True)
        .start()
    )


def bounded(value):
    number = int(value)
    if not 1 <= number <= 10000:
        raise argparse.ArgumentTypeError("Use 1..10000 records/offsets for the pilot.")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["replay", "consume"])
    parser.add_argument("--bootstrap", default="localhost:19092")
    parser.add_argument("--topic", default="argo.github.replay.v1")
    parser.add_argument("--limit", type=bounded, default=1000)
    parser.add_argument("--apply", action="store_true", help="Required to write replay records.")
    parser.add_argument("--replay-id", default="manual-replay")
    parser.add_argument(
        "--checkpoint", type=Path, default=Path("data/generated/streaming/checkpoint")
    )
    parser.add_argument(
        "--database", type=Path, default=Path("data/generated/streaming/events.sqlite")
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", args.replay_id):
        parser.error("Use a short alphanumeric replay ID.")
    scope, scope_hash = pilot.load_scope()
    if args.operation == "replay":
        pointer = json.loads(incremental.DEFAULT_POINTER.read_text(encoding="utf-8"))
        state, digest = incremental.load_approved(pointer, scope)
        events = state["events"][: args.limit]
        report = {
            "mode": "historical_replay",
            "source_state_sha256": digest,
            "records": len(events),
            "topic": args.topic,
            "apply": args.apply,
            "coverage_start": state["coverage_start"],
            "through_exclusive": state["through_exclusive"],
        }
        print(json.dumps(report, indent=2))
        if not args.apply or not events:
            return
        names = {r["name"]: r["repository_id"] for r in scope["repositories"]}
        now = datetime.now(UTC).isoformat()
        records = [
            (
                e["event_id"],
                json.dumps(envelope(e, names[e["repo_name"]], state, digest, args.replay_id, now)),
            )
            for e in events
        ]
        spark = session()
        try:
            publish(spark, records, args.bootstrap, args.topic)
        finally:
            spark.stop()
    else:
        # Linux file locking is released even after a killed consumer. One writer per checkpoint.
        import fcntl

        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        with (args.checkpoint.parent / (args.checkpoint.name + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            contract = bind(args.checkpoint, args.database, args.bootstrap, args.topic, scope_hash)
            sink = Sink(args.database, contract)
            spark = session()
            try:
                query = start(
                    spark, args.bootstrap, args.topic, args.checkpoint, sink, scope, args.limit
                )
                query.awaitTermination()
                print(
                    json.dumps(
                        {"mode": "historical_replay", "progress": query.lastProgress}, default=str
                    )
                )
            finally:
                spark.stop()


if __name__ == "__main__":
    main()
