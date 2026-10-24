# ARGO expansion: implementation and pilot runbook

## Goal and current status

Target: 500 versioned repositories and 90 complete UTC days, followed by scheduled
ingestion, Kafka/PySpark processing, Airflow orchestration and pipeline observability.
This change implements the scope registry and isolated, seven-day GCS pilot only.
No live cloud query, credit verification, bucket creation or dashboard promotion has
been performed by this change. The production report remains on its approved checkpoint.

## Milestones

1. Verify GCP credit balance, expiry, eligible services, billing project and region.
2. Run the 500-repository estimate; inspect estimated bytes and choose a query cap.
3. Land and inspect one seven-day pilot in a private US GCS bucket.
4. Implement resumable 90-day backfill with a generation-guarded approved cursor,
   cumulative cost accounting and overlap/repair policies.
5. Reconcile the expanded scope and publish versioned dashboard aggregates.
6. Add Airflow ingestion/backfill/validation/publication DAGs.
7. Add Kafka and PySpark with replay, deduplication, late-event handling and
   idempotent sinks; persist checkpoints outside disposable compute.
8. Benchmark recovery, throughput, processing latency and cost; extend report health.
9. Export a durable snapshot and shut down paid compute before credit expiry.

Each milestone must have actual evidence before being marked complete. Airflow runs
finite workflows; the stream consumer runs independently.

## Repository selection

`config/repository-scope-v1.json` pins 500 unique repository IDs and canonical names.
All 24 original repositories are preserved. Additional projects are selected by
round-robin from eight GitHub language/topic searches, at most 100 results each,
deduplicating IDs. The registry records the queries and selection date.
Discovery groups are ML, web, data science, developer tools, scientific computing,
automation, CLI and DevOps. Membership is a purposive, popularity-biased sample,
not a representative census of Python or a verified domain taxonomy.

Queries filter stable repository IDs. Renames do not lose earlier events; normalized
records retain the source repository name alongside the pinned display name.
The old FastAPI name is documented as an alias. Zero observed events do not remove
a selected repository or establish that the source captured every GitHub event.
The 500-repository dataset must not be compared directly to the old 24-repository
totals as evidence of organic growth.

## One-time cloud setup

The existing GitHub federation variables are reused:
`GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_ETL_SERVICE_ACCOUNT`.
The workflow remains at `.github/workflows/rebuild-data.yml` on main, preserving
the existing narrow WIF trust. No service-account key is needed.

Before a paid pilot:

- In GCP Billing, verify the actual remaining credit, expiration date, billing-account
  status and service eligibility. The reported INR 30,000 has not been independently
  verified. Use INR 5,000 as an initial project allocation, not a forecast or an
  automatically enforced spending cap. Other projects may share the credits.
- Create or choose a dedicated **US multi-region** GCS bucket in the billing project,
  with uniform bucket-level access and public access prevention. Keep the pilot private.
  Choose US to match the public BigQuery source; review compute placement later.
- Grant the existing ETL service account **Storage Object Creator on that bucket only**.
  The pilot needs create permissions, not project-wide storage administration.
  Existing BigQuery Job User/public-dataset access is reused.
- Set the repository Actions variable `GCP_DATA_BUCKET` to the bare bucket name.
- Add budget alerts and appropriate BigQuery quotas. Alerts alone do not stop usage.
  Every pilot data query separately enforces maximum bytes billed, up to 20 GB.
- Configure a 90-day deletion lifecycle on this dedicated pilot bucket to bound
  abandoned attempts. Export anything worth retaining before expiration. Review the
  policy when this bucket becomes a production checkpoint store.

This session has no authenticated GCP CLI/connector; cloud setup and credit checks
require access to the correct GCP project. Do not grant broad roles just to bypass
a failed permission check.

## Run the pilot after merging

1. Open **Actions -> Data maintenance (manual)** on main.
2. Select `pilot-dry-run`; set an explicit `refresh_end` (exclusive UTC), leaving
   yesterday and today unqueried. Example on 2026-10-24: `2026-10-23`.
   The query covers the preceding seven days.
3. Inspect the JSON report: scope SHA256, dates, SQL hash, project, location and
   estimated bytes. Dry run reads no event rows and writes no GCS objects.
4. Select `pilot-refresh` with the **same end date and unchanged scope**.
   Supply `maximum_bytes_billed` just above the estimate, at most 20,000,000,000.
   If the estimate exceeds the ceiling, stop and redesign/narrow the batch;
   do not bypass the guard.
5. Download the `argo-pilot-RUN_ID` report artifact. Inspect the manifest URI,
   source query job, actual bytes, observed repositories, accounts and daily counts.
6. Inspect the GCS objects before proceeding to the 90-day backfill milestone.

The apply run estimates again, checks the cap and writes a small storage preflight
marker before executing the paid query. Failed queries/downloads/uploads can still
incur charges. A retry is a new charged query unless the service serves a cache hit;
do not assume retries are free.

The source is GH Archive; the extraction uses the existing event-category SQL and
account exclusions. These are heuristics, not proof all retained accounts are human.
Source capture is not guaranteed complete. Queried zero-event dates are represented
explicitly; missing required daily tables fail the query.

## Storage contract and failure behavior

Each attempt uses:
`pilots/SCOPE_SHA/START_END/ATTEMPT_UUID/`

- `started.json`: configuration/permission preflight; not a successful checkpoint.
- `events.jsonl.gz`: normalized source extract, deduplicated on disk by event ID.
- `scope.json`: exact repository registry.
- `manifest.json`: written **last**, only after validation and completed uploads.

Every upload uses `if_generation_match=0`; existing objects are never overwritten.
The manifest contains compressed-data SHA256, query provenance, exact daily counts,
all 500 repository counts (including zeros), duplicate counts and distinct accounts.
Conflicting payloads for one ID fail validation. A partial attempt has no manifest
and must never be consumed. Multiple successful attempts of the same window are
alternatives, not additive data partitions. Later backfill code must select one
approved attempt and deduplicate overlaps; this pilot does not invent an approved cursor.

The pilot stores only the selected fields/event types after existing account filters;
it is not an unfiltered archive of all source payloads. Disk-backed SQLite avoids
holding the entire event extract in memory. Neither extracted events nor per-run
snapshots are committed to Git.

## Verification and future streaming semantics

Credential-free scope and 90-day batch planning:

```sh
uv run python -m etl.pilot_activity --plan-only --days 90 --end-date 2026-10-23
uv run pytest tests/test_pilot_activity.py
uv run ruff check .
uv run ruff format --check .
```

Tests cover scope integrity, exact source tables, UTC boundaries, repository renames,
duplicate/conflicting IDs, zero-activity coverage, billing guards, no-write dry runs,
storage preflight and publication failure. Cloud mocks do not establish live IAM
permissions, SQL validity at BigQuery or actual costs; those require the dry run/pilot.

GH Archive publishes hourly files. Source publication lag and processing latency
will be displayed separately. Historical replay will be explicitly labelled.
No claim of instant GitHub delivery or high availability is made for a single-VM demo.

References:
- https://www.gharchive.org/
- https://docs.cloud.google.com/bigquery/docs/best-practices-costs
- https://docs.cloud.google.com/storage/docs/request-preconditions
- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://airflow.apache.org/docs/apache-airflow/stable/index.html
