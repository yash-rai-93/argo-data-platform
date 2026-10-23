# Did an activity spike mean broader participation?

**Finding:** the October 21, 2026 event spike was concentrated in one repository
and one account. The daily contributor count decreased. Event growth alone would
have overstated the breadth of participation.

This is an **initial seven-day descriptive investigation**, not a four-week
comparison, causal explanation, productivity ranking, or current churn study.
Re-evaluate it after the approved 28-day backfill rather than extrapolating.

## Question and scope

Across the selected Python repositories, did the highest-volume day reflect
more contributors, or more events from a smaller set of contributors?

- Source: public GH Archive through the repository's BigQuery extraction.
- Snapshot: **[2026-10-15, 2026-10-22), UTC**, 1,050 events, 344 contributors.
- [Source extraction run](https://github.com/yash-rai-93/argo-data-platform/actions/runs/40009513670).
- Checkpoint SHA-256:
  `4cc9c9d2792d6ff93af0be5cea667856b2deedb55cacc01c233f2cf79eee6aba`.
- Unit: a unique archive **event ID**, not a commit, merged PR, unique issue,
  hour worked, or individual unit of useful contribution.

The script validates checkpoint/aggregate agreement before calculating results.
Dates are half-open; repository rename aliases are combined for attribution.
Daily contributor counts are distinct accounts, not sums of repository counts.

## Evidence

| Date (UTC) | Events | Distinct contributors |
| --- | ---: | ---: |
| October 15 | 87 | 55 |
| October 16 | 102 | 72 |
| October 17 | 54 | 42 |
| October 18 | 84 | 57 |
| October 19 | 173 | 87 |
| October 20 | 168 | 87 |
| October 21 | **382** | **72** |

October 21 contains **36.38%** of all events in the seven-day snapshot.
Compared with October 20, events increased by **214 (+127.38%)**, while
distinct contributors decreased by **15 (-17.24%)**. These are adjacent-day
descriptions, not seasonally adjusted changes or evidence of statistical significance.

| Event driver | October 20 | October 21 | Change |
| --- | ---: | ---: | ---: |
| PyTorch repository | 56 | 297 | +241 |
| All other scoped repositories | 112 | 85 | -27 |
| **Total** | **168** | **382** | **+214** |

PyTorch contributes **77.75%** of October 21 events. Its increase exceeds the
overall increase because activity elsewhere declined.

| Event category | October 20 | October 21 | Change |
| --- | ---: | ---: | ---: |
| Commit-category events | 71 | 307 | +236 |
| Pull-request-category events | 45 | 36 | -9 |
| Issue-category events | 31 | 22 | -9 |
| Engagement events | 14 | 9 | -5 |
| Release-category events | 7 | 8 | +1 |
| **Total** | **168** | **382** | **+214** |

One account generated **242 events (63.35%)** on October 21. Excluding that
account's events leaves **140 events**, below October 20's unadjusted 168.
This is a sensitivity check, not a fair adjusted comparison: the previous
day's largest account has not also been removed.

## Interpretation and limits

The observed growth is concentrated event volume rather than an increase in
the number of participating accounts. This supports inspecting activity mix
before interpreting the spike as broader community growth.

It does **not** establish why the account generated those events. Automation,
repository workflows, release timing, or concentrated human activity are
possible explanations requiring additional evidence. Bot-pattern and known-name
filters are incomplete; an account in the retained dataset is not proof of a
human contributor. Distinct event IDs do not rule out repetitive activity.

Seven days provide only one observation for each weekday. The comparison does
not control for weekday effects, source publication delays, or unusual releases.
The fixed repository scope is not representative of all open source. The
historical models and their 2023 evaluation results are independent of this case.

## Decision this could support

A maintainer reviewing the spike should inspect the dominant repository's event
mix and workflow context before allocating community-engagement resources.
Do not use raw event volume as a productivity score or contact an individual
solely because of this result.

After expanding to 28 days:

1. Compare equivalent seven-day windows and the same weekdays.
2. Recompute repository and account concentration across all four weeks.
3. Inspect the dominant event type, with documented automation exclusions kept
   consistent across comparison periods.
4. If a participation problem remains, propose a specific maintainer action,
   such as reviewing contributor onboarding friction.

An intervention has **not** been tested. A future evaluation could measure the
share of a defined contributor cohort that returns in a fixed follow-up window,
alongside unique contributors and activity concentration. Fix the cohort,
comparison design, and observation period before claiming improvement.

## Reproduce and extend

From the repository root, without cloud credentials:

```bash
uv run python -m etl.refresh_activity --validate-only
uv run python -m etl.investigate_activity
```

The output includes daily counts, peak-day concentration, exhaustive event
drivers, the checkpoint checksum, and source query provenance. It deliberately
omits account names from the concentration result.

The script analyses the **currently approved** checkpoint. To reproduce the
figures above after a later refresh, check out the snapshot associated with the
source run and verify the checksum. Run against the expanded approved snapshot
to produce new evidence; review the interpretation before publishing an update.
