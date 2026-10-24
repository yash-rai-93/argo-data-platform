# Publish the verified 90-day community report

## Current evidence and scope

Backfill run https://github.com/yash-rai-93/argo-data-platform/actions/runs/40110018483
completed all 13 batches over [2026-07-25, 2026-10-23) UTC, reporting 94,133 events
and 15,537,799,168 accounted query bytes against the 20 GB total budget.
The publication step independently rechecks the files; full-range distinct accounts
and observed repository counts are not inferred from per-batch sums.

## After merging the publication implementation

1. Open Actions -> Data maintenance (manual) -> Run workflow on main.
2. Select `community-publish`; set `refresh_end=2026-10-23`.
   Other query budget inputs are unused by this operation.
3. Run it. This reads the existing private GCS data; it makes no BigQuery calls.
4. Send the run link for review. Its summary contains the publication audit and
   a comparison link for a new `data/community-RUN-ATTEMPT` branch.
5. Open that comparison, create a pull request, wait for CI and merge.
   The PR changes only `data/community-source.json`.
6. After deployment/cache refresh, verify /community and /api/community totals,
   90 covered days, 500 repository options, cohort blanks, weekly changes, and
   the combined backfill byte total. Retain the publication audit as evidence.

No new IAM grant is needed beyond the bucket-scoped Storage Object User role
already required by the backfill. GCS bucket policies stay private.

## Verification and distribution

The publisher requires a complete checkpoint with no pending attempt and the exact
repository scope/query contract. It reads only approved manifest paths inside the
backfill prefix, verifies every compressed file SHA256, validates event IDs, fields,
repository IDs and UTC bounds, and recomputes each batch's daily, repository and
distinct-account counts. Conflicting cross-batch event IDs fail. Identical IDs are
deduplicated before calculating full-range counts.

The current serializer builds a bounded serving snapshot (maximum 64 MiB unpacked).
The published files contain documented **public GitHub event fields**, including public
account handles, event IDs and repository names. They exclude credentials, private GCS
checkpoint configuration and source payloads. Publishing this report creates public
GitHub prerelease assets; the original GCS objects remain private.

Assets:
- `recent-activity.json`: exact summary, quality evidence, backfill usage.
- `recent-activity-state.json.gz`: event-level serving index for exact interactive filters.
- `publication-audit.json`: full-range counts and verification provenance.

Large event snapshots are release assets, not Git blobs. Only a small versioned pointer
is committed. The pointer pins asset URLs and the summary checksum; the summary pins
the compressed event checksum. The route accepts only this repository's expected
release-asset URLs. Missing pointers retain the original approved report; malformed
or unavailable published sources fail closed rather than silently switching datasets.
Release tags include workflow run ID and attempt to avoid overwriting assets.

The dashboard supports all 500 selected repositories, including zero observed events.
Distinct accounts are recomputed for the selected dates/repositories/categories.
The return matrix expands to the observed week count with a scrollable layout.
Incomplete and future cohort cells remain blank. Query bytes are explicitly combined
across the 13 backfill batches. No incremental-refresh reconciliation is fabricated.
The 2023 model study and the older 24-repository investigation remain separate.

The home page's original recent-activity panel continues to show its separately
approved 24-repository refresh. The /community report identifies its own full coverage
and scope; its totals must not be interpreted as organic growth against that sample.

Publication and production activation are separate: a successful workflow prepares
assets and a pointer review branch; only merging the pointer activates those assets.
For rollback, revert the pointer commit or point to a previously verified release.
Keep referenced assets available. Never delete an active release to roll back.
