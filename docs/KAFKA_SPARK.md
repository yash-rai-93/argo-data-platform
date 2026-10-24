# Kafka and PySpark: bounded historical replay

## Scope and status

This is an isolated replay pipeline, not live GitHub ingestion. The producer loads
the approved 500-repository release, verifies its checksums/aggregates and sends
at most 10,000 selected events per invocation (default 1,000). It preserves original
event timestamps and adds historical_replay mode, replay ID, snapshot hash and
publication time. A publication timestamp does not turn old events into current activity.

Kafka buffers the records. PySpark Structured Streaming reads Kafka offsets, parses
the JSON schema, derives UTC event dates and passes bounded microbatches to a
transactional SQLite audit sink. Invalid records are quarantined. Original event
IDs deduplicate repeats across batches and later replays. Conflicting payloads for
an existing ID fail and roll back the entire batch.

The live community dashboard, incremental GCS checkpoint, Airflow DAG and 2023
model study are separate. No cloud service or continuously running process is
deployed by this implementation.

## Deliberate pilot limits

- Kafka 4.2.1, one broker/controller, replication factor one, persistent named volume.
  The host port binds to loopback. This is a trusted local sandbox without TLS/SASL,
  not an internet-facing or highly available broker.
- PySpark 3.5.6, Java 17, matching Kafka connector with Scala 2.12.
- Linux consumer with two local Spark threads, bounded available-now execution.
  It processes available offsets and exits. Run it again to drain later input.
- Persistent local checkpoint and SQLite database must stay together on one host.
  Consumer file locking prevents concurrent writers to the same checkpoint.
- maxOffsetsPerTrigger defaults to 1,000 and is configurable up to 10,000.
  The sink refuses a batch exceeding 20,000 rows. Kafka partition allocation can
  make the offset limit approximate.
- SQLite is an explicit single-driver pilot sink. Spark does distributed parsing,
  but this does not demonstrate distributed sink throughput or require Spark at
  the current dataset volume.
- Seen event IDs remain in the durable sink instead of an event-time watermark.
  Historical out-of-order replay is retained; no claim of bounded production
  deduplication state or long-term storage lifecycle is made.

## Sandbox runbook after merge

Use a Linux host with Docker Compose, Java 17 and uv. Run from the repository root.
No GCP credential or BigQuery query is required for this public-snapshot replay.

Start Kafka:

    docker compose -f streaming/compose.yml up -d --wait
    docker compose -f streaming/compose.yml exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic argo.github.replay.v1 --partitions 2 --replication-factor 1 --config retention.ms=604800000

First inspect a replay plan. This downloads and validates the approved snapshot;
it does not start Spark or write Kafka records:

    uv run --no-project --python 3.12 --with pyspark==3.5.6 python -m streaming.spark_replay replay --limit 1000 --replay-id demo-1

Then write the capped replay and consume it:

    uv run --no-project --python 3.12 --with pyspark==3.5.6 python -m streaming.spark_replay replay --limit 1000 --replay-id demo-1 --apply
    uv run --no-project --python 3.12 --with pyspark==3.5.6 python -m streaming.spark_replay consume

Outputs default to data/generated/streaming/events.sqlite and its adjacent
checkpoint directory, outside tracked Git files. Repeat consume to resume offsets.
Repeat replay to test deduplication; producer writes are at least once.

Stop the broker when finished:

    docker compose -f streaming/compose.yml down

That command preserves the named volume. Keep the broker volume, Spark checkpoint
and sink for recovery testing; do not delete checkpoints to resolve errors.
An absent sink, changed topic/scope/paths, missing binding or changed batch content
fails rather than silently resetting offsets. If first-time initialization was
interrupted before the sink existed, inspect that incomplete setup before retrying.

## Verification evidence

Credential-free unit tests exercise malformed messages, scope/category/timestamp/key
checks, conflicting IDs, batch rollback, repeated batches, changed Kafka offsets,
late historical events and checkpoint/sink identity binding.

The separate CI streaming job starts a real broker, sends **synthetic** fixtures and
runs the actual Spark Kafka connector. It injects a failure after sink commit but
before Spark batch checkpoint completion, restarts, checks stable counts, restarts
without input, and replays duplicate records. Expected final counts are three unique
events, four quarantined records and twelve consumed Kafka records. These are test
fixtures, not measured GitHub community activity.

The SQLite batches table records input, new, duplicate and invalid counts per batch.
The messages table identifies Kafka topic/partition/offset; events contains deduped
source fields; quarantine retains malformed payloads and reasons for inspection.
A batch ledger retry returns the original receipt and does not increment counts.
Spark progress logs expose processed offsets and batch metrics. Historical event age
must never be reported as live source latency.

Production credit usage, sustained throughput, VM crash recovery, durable cloud
storage and live ingestion remain unmeasured. A later deployment must choose those
requirements explicitly and record evidence before claiming real-time delivery.

Official references:

- https://spark.apache.org/docs/3.5.6/structured-streaming-programming-guide.html
- https://spark.apache.org/docs/latest/structured-streaming-kafka-integration.html
- https://kafka.apache.org/community/downloads/
