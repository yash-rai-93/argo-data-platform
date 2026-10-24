# Operational evidence

## What can be measured now

The streaming CI job runs a real Kafka broker and the actual PySpark Kafka connector
against synthetic historical events. It now emits a machine-readable evidence JSON
artifact, retained for 90 days. Completed run results should also be committed here
with their immutable run link so the evidence outlives artifact retention.

Measurements:

| Area | Measurement | Meaning |
| --- | --- | --- |
| Throughput | Three sequential trials of 1,000 unique records each | Observed available-now consumption rate including query startup, after warmup |
| Replay delay | Publication to last sink commit per trial | Includes producer time and deliberate waiting before starting the consumer |
| Recovery | Failed-query termination to completed checkpoint recovery | One injected failure after sink commit; verifies no double counting |
| Failure behavior | Quarantine, conflicting-ID rollback, offset/checkpoint guards | Controlled tests, not a production failure rate |
| Runtime | Spark initialization, individual operations and total harness time | CI runner and dependency cache affect these results |
| Costs | GCP use flag; unverified currency costs remain null | CI timings are not a cloud billing receipt |

The report records commit, run ID, Python/platform/CPU information, Spark/Kafka
versions, local Spark threads, broker/partition count and the single-driver sink.
Each trial records bytes, producer/consumer durations, rate and Spark input rows.
The benchmark asserts exactly 1,000 additional messages and unique events per trial.

## What this evidence does not establish

Three small trials on a shared CI runner do not establish peak capacity, production
sizing, sustained throughput, p95/p99 message latency, uptime or an SLA.
The SQLite driver sink is a bounded single-host audit sink; this is not a benchmark
of a distributed sink.

The recovery test fails a Spark callback after the SQLite transaction commits.
It does not kill the host, lose a disk or broker, or test multi-node failover.
Checkpoint recovery, event-ID deduplication and broker replication are different
properties and must not be presented as equivalent.

Historical event age is not live source lag. Replay delay uses publication time;
original GitHub timestamps remain unchanged. Actual source lag needs a live source
and a recorded collection/publication timestamp.

No GCP resources are provisioned by the CI benchmark. GCP currency costs and GitHub
Actions account billing are unverified and remain null. A BigQuery byte cap is not
a universal rupee spending cap.

## Remaining deployment evidence

After the next eligible incremental source window:

1. Run the incremental dry run, review its estimate, then run an explicitly capped apply.
2. Save the actual BigQuery job ID, processed/billed bytes and publication audit.
3. Deploy the Airflow/runtime pilot with an approved identity and resource configuration.
4. Capture Cloud Billing costs by resource/project/date, including compute, disk,
   GCS, BigQuery and network usage; credits consumed and cash charged are separate.
5. Measure live source lag separately from broker-to-sink processing delay.
6. Exercise process restart, broker restart and host recovery separately; record
   which storage survives each failure and whether any records were lost or repeated.
7. Compare measured usage and costs with the selected pilot allowance before scheduling.

The first eligible incremental daily window on October 25, 2026 opens at 05:30 IST.
Synthetic replay measurement can proceed before that; it does not advance source coverage.
