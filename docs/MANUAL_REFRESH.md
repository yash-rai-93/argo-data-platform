# Manual incremental activity refresh

Use **Actions → Data maintenance (manual)** on `main`. There is no cron,
background poller, runtime BigQuery call, or automatic model retraining.

## First refresh, and each later refresh

1. Run with `operation=incremental-dry-run`. Leave the cap blank.
   The run summary shows exact UTC dates, estimated bytes, and the query hash.
   This is BigQuery's estimate-only mode: it does not download event rows.
2. Review the estimate. Run again with `operation=incremental-refresh`,
   copy the reported `end_exclusive` into `refresh_end`, and enter an explicit
   `maximum_bytes_billed` slightly above the estimate, up to `20000000000`
   (20 GB). That number is a query limit, not a rupee amount or spending target.
   The apply run estimates again and refuses an estimate above your cap.
3. Follow the compare link in the successful run summary. Open a pull request
   from `data/manual-refresh` to `main`. It must change only
   `data/recent-activity.json` and `data/recent-activity-state.json.gz`.
   Review the coverage and actual billed bytes, wait for CI, and merge.
   Opening this PR yourself also starts CI (the Actions token's branch push
   does not recursively start workflows).
4. The existing deployments pick up the merged snapshot through their usual
   main-branch deployment process. Check
   `https://argo-api-yash.onrender.com/api/v1/activity/recent` and the dashboard's
   **Recent GitHub activity** panel. Its coverage and update timestamp must
   match the merged file. Run **Verify live deployment** for the full smoke check.

The existing GCP project variables, service account, and WIF provider are reused.
The workflow path remains `.github/workflows/rebuild-data.yml` on `main`,
matching the existing federation restriction. No new IAM grants, keys,
bucket, database, or paid always-on service are required.

## Expand the initial snapshot to 28 complete days

1. After this implementation is merged, run `backfill-dry-run` on `main`.
   Set an explicit exclusive UTC end date, or use the safe publication-lag default.
2. Review its start, end, and byte estimate. Run `backfill-refresh` with the
   **same end date** and an explicit query cap chosen from that estimate.
3. Review and merge the two-file data PR as usual, then verify the deployed panel.

Backfill reads one continuous 28-day range. It merges by event ID, preserves
earlier retained coverage, and never moves the approved end cursor backwards.
If the requested range would leave a gap after a long pause, catch up with normal
incremental batches first. An already covered schema-v2 backfill is a no-op.
Both operations share the existing spending checks, pending-branch guard,
31-table query ceiling, and WIF workflow. No schedule or new service is added.

A successful query generates schema-v2 aggregates containing weekly comparisons
and quality evidence. Legacy checkpoints remain readable and are upgraded on
the next successful apply. Legacy coverage is inherited explicitly; detailed
historical deduplication counts are not fabricated. Schema-v2 covered-day lists
must match the continuous retained range. A zero-event queried day remains
covered; a missing required source table fails the query.

The weekly view uses the last 14 covered days, split into two equal periods.
It is unavailable before 14 days. Repository and category tables are exhaustive
additive event changes; distinct contributors are counted across repositories,
not summed. Percent changes are null when the previous count is zero.
Freshness is data age, separate from validation and manual catch-up status.

## What is fetched and retained

- The historical repository scope is reused, including the current
  `fastapi/fastapi` name alongside its old `tiangolo/fastapi` alias.
- First run: seven recent days, independent of the old July–December 2023 study.
  It never attempts to fill the gap between 2023 and today.
- Subsequent runs: start at the last **approved** exclusive-end cursor, re-read
  two preceding days for late arrivals, then upsert by stable `event_id`.
  A source correction for an existing ID replaces that event. Corrections or
  late arrivals older than the overlap require a separately planned repair.
- Leave yesterday and the current UTC day unqueried for publication lag.
  Concrete daily table names handle year boundaries and fail if any required
  source table is missing; a failed query never advances the cursor.
- At most 31 daily tables per run. After a long pause, the run may report
  `caught_up=false`. Merge that batch, then estimate and apply the next batch.
  Dates are never silently skipped. An equal end cursor makes no BigQuery call.
- Retain up to 90 covered days. Daily counts include zero-event days; the UI
  labels the actual coverage rather than presenting a partial week as 30 days.
  Both the compressed event checkpoint and its small aggregate are committed
  together. A checksum and recomputation verify they match.
- The API image contains only the small aggregate. Visitors cannot trigger a
  refresh and no GCP credential is present in the serving container.

The model warehouse, training features, Cox baseline, model cards, holdout
metrics, anomaly decomposition, and retention queue remain the fixed 2023 study.
The new panel reports recent activity; it makes no claim about current model
accuracy or current contributor churn.

## Failure recovery and costs

A failed query, cap check, validation, or publication leaves the approved
checkpoint on `main` intact. A successful query can still incur usage if a later
test or branch push fails; inspect the job logs before retrying. The bytes cap
applies to the single data query, not every possible charge in the billing
account. Data transfer, Actions allowances, build limits, and hosting are separate.

A pending data branch blocks further queries until it is merged. To discard an
unwanted batch, close its PR and delete `data/manual-refresh`; the next run resumes
from the approved checkpoint. Discarding a batch means its dates will be queried
again. After merging, deleting the branch is optional: a later run can reuse it
only if its snapshot files match `main`, with an explicit force-with-lease on that
dedicated branch. Main itself is never force-pushed. Runs queue rather than
cancel one another, and a main-branch change during extraction prevents publishing
a stale branch.

Run manually before a demo when needed. No fixed fee is added per trigger;
query bytes and other metered usage determine cost after applicable free
allowances/credits. Do not assume all refreshes are free. If an estimate exceeds
20 GB, stop and narrow the planned source scope or review the design rather than
bypassing the built-in ceiling. The first seven-day extraction is recorded in the README. The new 28-day
backfill requires its own dry run and explicit cap before extraction.

The repository is the checkpoint store for this low-frequency portfolio demo.
Keeping only 90 days bounds each snapshot; Git history still grows per refresh.
Move checkpoints to object storage before adopting frequent automated refreshes.

For local validation without cloud credentials:

```powershell
uv run python -m etl.refresh_activity --validate-only
uv run pytest
```

Historical operations `dry-run` and `rebuild` still exist in the same workflow.
They rebuild the historical training artifacts and are not incremental refreshes.

References:
[GH Archive publication](https://www.gharchive.org/),
[BigQuery cost controls](https://cloud.google.com/bigquery/docs/best-practices-costs),
[GitHub token event behavior](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow).
