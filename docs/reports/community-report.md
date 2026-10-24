# Interactive GitHub contributor report

The report is available at /community, linked from the recent-activity panel.
It contains Community Overview, Participation & Concentration, and Data Trust &
Pipeline Health. These pages analyze the recent approved GH Archive checkpoint,
separately from website tracking and the 2023 training study.

## Data flow

The browser applies date, repository and event-category filters through the
same-origin GET /api/community route. The route reads the public committed
recent-activity summary and compressed checkpoint from the repository's main
branch, verifies the compressed SHA-256, schema, retained IDs, source coverage,
all totals and every daily aggregate, then returns report aggregates.
It never runs BigQuery, changes a source cursor, or trains a model.

Upstream HTTP responses and the verified decoded source have five-minute
caches. An unavailable or mismatched checkpoint yields a retryable 503, rather
than fabricated or partially published data. Invalid filter values yield 400.
The report can be used without a Mixpanel subscription or token.

## Metric definitions

- All source-date comparisons use UTC. Dates in the UI are inclusive; the
  implementation uses half-open [start, end + 1 day) ranges.
- Events are source event occurrences. PR/issue events are pull_request + issue;
  they are not merged PRs or unique issues.
- Distinct contributors are source account logins, deduplicated across the
  selected rows. Do not sum daily or repository unique counts.
- Repository/category filters apply before the date selection. Rankings and
  concentration shares are recalculated for the selected event set.
- Weekly comparisons require at least 14 selected days. The latest seven days
  are compared with the preceding seven, ending at the inclusive date filter.
  A zero previous baseline leaves percent change unavailable.
- Returning accounts appear in both weeks; joining accounts occur in the
  latest week but not the preceding week; absent accounts occur in the
  preceding week but not the latest. Joining is not new to open source;
  absence is not churn.
- Cohorts use first appearance in the retained snapshot after repository and
  category filters, before date filtering. Only complete observed seven-day
  source periods receive counts. Unavailable or partial cells remain blank.
- The October 14 and October 21 investigation follows current scope filters.
  A day outside the date selection is marked unavailable.
- Source validation, coverage and query bytes describe the full checkpoint,
  not a filtered subset. Only the latest recorded refresh is shown.

## Verification

Frontend tests reconcile the approved snapshot totals, daily counts, weekly
changes, overlap, cohort cells and concentration; cover date boundaries,
filter intersections, empty selections and invalid inputs; and verify API
caching and checksum rejection. CI also starts the production build and runs
tests/community_browser.cjs across all three pages, repository selection,
empty states, date validation, cohort blanks and mobile overflow.
Browser screenshots and the result JSON are retained as CI artifacts.

Run from frontend:

    node --test tests/*.test.mjs
    npm run lint
    npm run build

The initial approved snapshot is Sep 24 through Oct 21, 2026 UTC:
5,657 events, 1,116 accounts and 2,174 PR/issue events. Latest-week deltas
reconcile to -34.62%, -10.65% and +4.00%. Golden regression checks record this
snapshot; update the regression fixture expectations deliberately when the
approved observation window changes.
