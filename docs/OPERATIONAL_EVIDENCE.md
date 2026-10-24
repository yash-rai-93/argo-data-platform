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

## Recorded sandbox result

Evidence: [CI run 40124551182](https://github.com/yash-rai-93/argo-data-platform/actions/runs/40124551182),
with [the complete measured JSON](evidence/streaming-ci-40124551182.json).
The run passed on October 25, 2026 IST (October 24 UTC), using Python 3.12.15,
PySpark 3.5.6, Kafka 4.2.1, two local Spark threads, two Kafka partitions, one
broker and a SQLite driver sink. The shared CI host reported four logical CPUs.

| Trial | Unique input records | Consumer duration | Observed records/second | Publication to last sink commit |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1000 | 1.415 s | 706.643 | 1.604 s |
| 2 | 1000 | 1.345 s | 743.439 | 1.518 s |
| 3 | 1000 | 1.560 s | 640.931 | 1.741 s |

Median observed rate: **706.643 records/second**, after warmup. Each trial carried
543,580 key/value bytes; producer durations were 0.200-0.227 seconds.
Consumer durations include available-now query startup and exclude producer/JVM startup.
Publication-to-commit delay includes the producer and deliberate pre-consumer waiting.

The controlled failure occurred after the sink commit. Checkpoint restart completed
in **1.334562 seconds**. Restart without input took 0.069408 seconds and added no rows.
Duplicate replay preserved three unique fixture events; malformed input was quarantined.
After all trials, reconciliation was **3,003 unique events, 4 quarantine records and
3,012 Kafka records**. These counts include the recovery fixtures and synthetic trials.

Spark initialization took 12.449 seconds; total harness time was 25.156 seconds.
These values are observations of this CI run, not a capacity limit or production SLA.

### Existing query-byte evidence

The checksum-verified [published backfill summary](https://github.com/yash-rai-93/argo-data-platform/releases/download/community-data-40112298324-1/recent-activity.json)
records **15,537,799,168 billed BigQuery bytes** against a **20,000,000,000-byte cap**
for the 13-batch July 25-October 22 snapshot. Processed bytes were 15,532,379,573.
This is query usage evidence, not an INR cost calculation or Cloud Billing receipt.
The replay benchmark used no GCP resources; currency costs remain unverified.

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
