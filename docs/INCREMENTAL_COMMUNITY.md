# Incremental ingestion for the 500-repository report

## What advances

The approved source is the release pinned by **data/community-source.json on main**.
The original 24-repository home-page sample and the 2023 training data are separate.
Each candidate uses the same 500 stable repository IDs and category/account filters
as the approved backfill. No repository discovery or model training happens here.

A refresh queries two previously covered UTC days plus up to five new days, using
at most seven exact GH Archive daily tables. It retains 90 continuous UTC days.
Overlapping IDs are counted once; late additions within the overlap are accepted.
Previously observed events are retained if an overlapping source query omits them.
A changed payload for an existing ID fails validation rather than silently changing
history. Arrivals older than the two-day overlap need a separate repair procedure;
this job does not establish complete capture of all GitHub activity.

An end equal to the approved cursor is a no-op, before creating cloud clients.
An older end is refused. Yesterday and today remain unqueried in UTC to allow
source publication. This is incremental daily batch ingestion, not real-time delivery.

## First run after merging the implementation

1. Open **Actions -> Data maintenance (manual) -> Run workflow**. Select **main**.
2. Select **community-incremental-dry-run**. Leave **refresh_end** blank to use the
   latest permitted end, or enter an exclusive UTC date.
3. Leave **maximum_bytes_billed** blank. Set **total_max_bytes_billed** to
   **10000000000**; leave **retry_failed** false. **max_batches** is unused here.
4. Read the job summary. Check project, base-state hash, planned dates, estimate and
   whether it is caught up. Dry run downloads and validates the approved public
   snapshot and reads any private checkpoint; it does not read event rows from
   BigQuery, write GCS objects, or publish a release.
5. If the result is **no_op**, stop: the approved report is already current under
   the source-lag policy. With the initial cursor of **2026-10-23**, a run on
   **2026-10-24 UTC** is a no-op. The next eligible end is **2026-10-24** on
   **2026-10-25 UTC**. All boundaries in this runbook use UTC.
6. For an actual estimated window, select **community-incremental-refresh**.
   Copy **requested_end** from the estimate into **refresh_end**. Keep the same
   total cap and choose **maximum_bytes_billed** above the estimate, allowing
   BigQuery billing rounding. Both caps must be positive and at most
   **20000000000 bytes**. Do not guess a cap before inspecting the estimate.
7. The job validates the landed extract, reconciles IDs and writes a candidate
   release plus a small pointer branch. Open the comparison link in its summary,
   create a PR, wait for CI, and merge it to update **/community**.
8. Check the production report's end date, totals and Data Trust reconciliation.
   If **caught_up** is false, repeat from the newly merged pointer to advance the
   next bounded window. Close superseded pointer PRs; promote only a candidate
   built from the currently approved pointer.

The query caps bound BigQuery bytes, not rupees or all cloud spending. The total
cap covers this specific base-state/window execution and its retries, not all
future incremental runs. GCS, networking and hosting are separate. No recurring
schedule or always-on compute is enabled by this change.

## Retry and failure behavior

The execution key pins the billing project, US location, base-state SHA256, scope
SHA256, query-contract SHA256 and effective query window. Its private checkpoint is:

    gs://BUCKET/incremental/EXECUTION_SHA256/checkpoint.json

The existing backfill controller is reused for query execution:

- A generation-guarded GCS reservation persists the job ID and full query cap
  **before** submitting a data query.
- Re-running the same execution reattaches to that job. A completed execution
  reuses its manifest and extract, without another data query.
- The checkpoint's total cap is pinned at the first apply. Reuse that value.
- A missing old pending job is not automatically resubmitted after 24 hours.
- A confirmed failed job needs explicit **retry_failed=true**. Its full reserved
  cap remains accounted. That invocation records the failure; the next invocation
  reserves the replacement if budget remains. Do not enable this for a running
  or merely slow job.
- Checksums, per-day/per-repository counts, distinct accounts, category mapping,
  scope, timestamps, ID conflicts and 90-day continuity must pass before a
  candidate is written.
- A stale main commit is refused before querying and before release publication.
  Query completion alone never advances the approved report cursor.

A failed validation leaves the current report available. Inspect the failure;
do not delete checkpoints or change hashes to force publication. Keep lifecycle
deletion rules away from active **backfills/** and **incremental/** checkpoints.

Only public GitHub fields already approved for the report become release assets.
Private GCS extracts remain private. Keyless federation and the existing narrowly
trusted main-only workflow path are reused; no new GCP role or secret is required.

## Evidence and limits

The Data Trust panel receives incoming rows, duplicate incoming IDs, overlap IDs
and new IDs. The attached audit also records expired IDs, previous/retained totals,
query job, actual bytes, source commit, scope and predecessor hashes.

Reconciliation:

    retained events = previous events - expired IDs + new IDs

Tests use synthetic data and cover late arrivals, overlap, expiration, empty
source days, rejected conflicts, corruption, scope mismatch, bounded catchup,
no-write dry runs, and completed-query reuse. They do not prove live IAM, current
source availability, or actual cloud billing. The first successful cloud apply
and production check remain required deployment evidence.

Airflow orchestration is the next milestone. It can invoke this bounded ingestion
entry point; Kafka/PySpark and recovery benchmarks remain later work.
