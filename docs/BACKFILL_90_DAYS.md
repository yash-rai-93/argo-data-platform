# Resumable 90-day backfill

## Prerequisites and current evidence

The seven-day pilot succeeded in run
https://github.com/yash-rai-93/argo-data-platform/actions/runs/40103121780:
4,009 events, 1,677 distinct accounts, 238 of 500 repositories with observed
activity, zero duplicate source IDs, and 422,576,128 billed bytes.
This is pilot evidence, not a 90-day result. The 90-day backfill has not yet run.

Use project `argo-data-yash-93`, private bucket `yash-argo-pilot-20261024`,
and ETL account `argo-etl@argo-data-yash-93.iam.gserviceaccount.com`.
Keep the existing WIF configuration and `GCP_DATA_BUCKET` variable.

**One permission change is required:** open the bucket's Permissions tab, find the
ETL service account, edit its role to **Storage Object User**, and save. This is
bucket-scoped, not a project-wide role. The pilot's Object Creator role cannot read
or update the persistent checkpoint. No service-account key is needed.

Review the bucket lifecycle policy: do not expire active backfill checkpoints or
approved data during the demo. The pilot's optional 90-day deletion policy should
be scoped to `pilots/`, not `backfills/`. Export data before credit expiry and
review retention before automated production ingestion.

## Step-by-step execution after merging

1. Open **Actions -> Data maintenance (manual) -> Run workflow**, branch `main`.
2. Choose `backfill90-dry-run`.
3. Set `refresh_end=2026-10-23`. This pins the full 90-day range
   **[2026-07-25, 2026-10-23) UTC**, split into 13 contiguous, non-overlapping batches.
4. Leave `maximum_bytes_billed` blank. Keep
   `total_max_bytes_billed=10000000000` (10 GB), `max_batches=3`,
   and `retry_failed=false`. The total is a planning ceiling, not an INR value.
5. Run and review all batch estimates. Choose a per-batch cap above the largest
   estimate, allowing billed-byte rounding. Each query and the entire backfill
   are capped at no more than 20 GB. Do not bypass a failed estimate.
6. Choose `backfill90-refresh` with the **same end date and total budget**.
   Enter the reviewed `maximum_bytes_billed`. Leave `max_batches=3`.
7. Inspect the report: completed count, approved-through cursor, accounted bytes,
   and checkpoint URI. Rerun with the same settings until `stage=complete` and
   `batches_completed=13`. Already approved batches are skipped.
8. Do not run a new end date to resume: that creates a separate backfill identity
   and budget. Keep the scope, query contract, project, end date and total budget pinned.

No automatic schedule is added. The default performs up to three batches per
invocation; an explicit `max_batches` from 1 to 13 is supported. Dry run estimates
all remaining batches, including a possibly already submitted pending batch, so
its total is conservative and is not an invoice prediction. It reads checkpoints
but writes no objects and runs no data query.

The successful pilot is stored separately and is not added to the backfill totals.
Its window overlaps this backfill, but only the approved backfill manifests count.
No production dashboard or model artifact is modified.

## Recovery and budget contract

A backfill ID hashes the project, repository scope, 90-day windows, location and
rendered query contract. Its prefix is `backfills/ID/`.

`checkpoint.json` contains contiguous completed batches, any pending attempt,
failed attempts, the pinned total budget and each completed manifest reference.
Writes use GCS generation preconditions: a stale writer fails before advancing state.
The existing workflow concurrency group also serializes maintenance runs.

Before submitting a paid query, the checkpoint reserves the **entire query cap**.
Unknown/interrupted attempts remain reserved. On successful validation, the reservation
is replaced by actual billed bytes. Failed attempts are conservatively charged at
their entire reserved cap, even if BigQuery reports less. The budget only covers
queries in this backfill identity; storage, network, other jobs and separate backfills
are outside this byte limit.

Every pending attempt has a persisted BigQuery job ID. Reruns reattach to that job.
Duplicate submission responses reattach as well; automatic job-level retries are
disabled. A missing job older than 24 hours is not automatically resubmitted.
Expired query results or validation failures stop with the pending reservation intact;
do not delete the checkpoint to force progress.

If a BigQuery job itself is confirmed failed, inspect its error first. Only after
correcting the cause, rerun with `retry_failed=true`. This explicitly abandons that
failed job, retains its full cap in accounting, and allows a new reservation on a
subsequent loop/invocation. It does not advance coverage. Ambiguous network failures
are resumed using the same job ID, not replaced with a new charged attempt.

Event uploads are immutable and checksummed. An interrupted upload is accepted on
resume only if its downloaded SHA256 matches the re-materialized source rows.
Batch manifests are published last. A manifest published before an interrupted
cursor write can be adopted on resume without re-querying events. Completed windows
are disjoint; distinct-account counts must still be recomputed across windows, never
summed. Repository and daily counts reconcile with each batch's event total.

There is no dashboard promotion in this milestone. A later publication step must read
only approved manifests, verify event checksums, deduplicate IDs across partitions,
and calculate exact full-range account/cohort metrics. Source completeness, late
source corrections and incremental overlap/repair remain separate concerns.

## Validation

Credential-free tests:
`uv run pytest tests/test_backfill_activity.py tests/test_pilot_activity.py`.

Tests cover cumulative reservations, interrupted uploads and cursor writes, repeated
runs, no-op completion, generation conflicts, pinned settings, malformed manifests,
query job reuse, duplicate job submission and explicit failed-job replacement.
Live IAM, 90-day table availability and byte estimates require the new dry run.

References:
- https://docs.cloud.google.com/storage/docs/request-preconditions
- https://docs.cloud.google.com/bigquery/docs/running-jobs
