# Activity concentration and weekly participation

**Finding:** raw event volume exaggerates the size of the latest weekly activity
decline. Events fell **34.62%**, distinct contributors fell **10.65%**, and
PR/issue-category events increased **4.00%**. Much of the event-count decline
is concentrated in one repository and the commit category.

This is a **28-day descriptive investigation**. It does not establish a cause,
measure developer productivity, evaluate an intervention, or measure current
model accuracy.

## Question and data

Did recent changes represent broad participation changes, or concentrated
event volume? Does the October 21 spike still look exceptional with four weeks
of context?

| Evidence | Recorded value |
| --- | --- |
| Source | Public GH Archive through BigQuery; the same curated Python repository scope |
| Coverage | **[2026-09-24, 2026-10-22), UTC**: 28 complete queried days |
| Events | **5,657** unique retained event IDs |
| Contributors | **1,116** distinct account logins across the entire window |
| PR/issue-category events | **2,174** |
| Source run | [Manual backfill 40021018408](https://github.com/yash-rai-93/argo-data-platform/actions/runs/40021018408) |
| Matched snapshot | [Aggregate at d7e27eb](https://github.com/yash-rai-93/argo-data-platform/blob/d7e27ebe3b7d665fb7642a8cfad9497f7a15fbf5/data/recent-activity.json) |
| Checkpoint SHA-256 | `6b1002a3c31f8f1eb35c1eafe9912c1b24894bb97b7b7a3637eb970178e2803b` |

All 28 expected daily source tables were successfully queried. The refresh
recorded zero duplicate incoming IDs, 1,050 IDs overlapping the previous
checkpoint, and 4,607 new IDs. All five snapshot checks and all 54 Python tests
passed during the refresh. The checkpoint and aggregate agree.

These checks establish query coverage and internal consistency. They do not
prove that GH Archive captured every GitHub event or that every retained account
is human. Bot-name and bot-pattern filters are incomplete.

## Four-week context

Each row below is seven complete UTC days. Contributor counts are distinct
within each row; the same person can appear in several rows, so the rows must
not be summed to obtain total distinct contributors.

| Period (inclusive dates, UTC) | Events | Distinct contributors | PR/issue events |
| --- | ---: | ---: | ---: |
| September 24–30 | 1,450 | 385 | 599 |
| October 1–7 | 1,551 | 434 | 708 |
| October 8–14 | 1,606 | 385 | 425 |
| October 15–21 | 1,050 | 344 | 442 |

The latest week has lower total volume and fewer participating accounts than
the preceding week, while PR/issue-category event volume is slightly higher.
The counts therefore do not support describing the change as a uniform collapse
across activity types.

These are activity **events**. A push event is not a commit count; PR/issue
categories include multiple event types and do not count unique PRs, merged
changes, resolved issues, or completed work.

## What drove the weekly change?

| Repository group | October 8–14 | October 15–21 | Event change |
| --- | ---: | ---: | ---: |
| PyTorch | 1,000 | 545 | -455 |
| All other scoped repositories | 606 | 505 | -101 |
| **Total** | **1,606** | **1,050** | **-556** |

PyTorch accounts for **81.83%** of the net event decline. This is an additive
description of where the change occurred, not a causal attribution.

| Event category | October 8–14 | October 15–21 | Change |
| --- | ---: | ---: | ---: |
| Commit | 960 | 475 | -485 |
| Release | 74 | 23 | -51 |
| Engagement | 147 | 110 | -37 |
| Issue | 138 | 147 | +9 |
| Pull request | 287 | 295 | +8 |
| **Total** | **1,606** | **1,050** | **-556** |

The repository and category tables are different breakdowns of the **same**
event decline; their effects must not be added together.

Of the preceding week's 385 contributors, **106** were also active in the
latest week: an observed return share of **27.53%**. There were 238 accounts
active only in the latest week and 279 active only in the preceding week.
The identities reconcile: `106 + 238 = 344` and `106 + 279 = 385`.
Joining means absent from the prior week, not new to the repository; a week's
absence does not establish churn.

## Revisit the original activity spike

The initial seven-day investigation identified October 21 as its largest day.
With 28 days available, **October 14 is the largest day**, with 457 events.
The earlier statement was specific to its seven-day window.

| Measure | October 14 | October 21 |
| --- | ---: | ---: |
| Events | 457 | 382 |
| Distinct contributors | 92 | 72 |
| PyTorch events | 337 | 297 |
| Largest single-account event count | 256 | 242 |
| Largest account's share of daily events | 56.02% | 63.35% |

Both days have concentrated volume. This is evidence of concentration, not
proof that the same account, automation, or a release caused both spikes.

A sensitivity check removes each day's largest account independently:

| Adjacent-day comparison | Raw event counts | Counts after removing each day's largest account |
| --- | --- | --- |
| October 13 → 14 | 280 → 457 | 205 → 201 |
| October 20 → 21 | 168 → 382 | 134 → 140 |

The large raw spikes become small changes under that exclusion. This is a
descriptive sensitivity check using an account selected from each observed day,
not a counterfactual or a reason to discard that account's work. The check
demonstrates how strongly event totals depend on concentrated activity.

## Decision and proposed follow-up

A maintainer should inspect PyTorch's event mix and workflow context before
treating the overall event decline as a community-wide participation problem.
The latest week's PR/issue events did not decline, while contributor count
declined less than raw volume. A dashboard alert based only on total events
would omit that distinction.

A reasonable follow-up is to inspect unique PR/issue items and documented
automation identities, applying any revised definitions consistently to both
periods. Repository-level participation should be reviewed alongside event
volume before proposing an onboarding or engagement intervention.

No intervention has been run. If one is proposed, predefine the contributor
cohort, action, comparison design, and follow-up period. Measure cohort return
share, unique contributors, and activity concentration rather than claiming
success from a larger event count alone. Do not contact or rank individuals
solely from these descriptive signals.

## Limits

- Four weeks provide four observations per weekday, not long-term seasonality.
- The repositories were curated, not sampled to represent all open source.
- Archive delays, platform workflows, and imperfect automation filters can affect
  counts. A successful query is not a completeness guarantee.
- Contributor overlap is limited to the scoped repositories and observed weeks.
  No causal or statistical-significance claim is made.
- The 2023 model cohort, training, and evaluation metrics are independent of
  this recent snapshot. No models were retrained by the backfill.

## Reproduce

The report is tied to the immutable snapshot commit above. To reproduce in a
separate checkout:

```bash
git worktree add --detach ../argo-investigation d7e27ebe3b7d665fb7642a8cfad9497f7a15fbf5
cd ../argo-investigation
uv sync --frozen
uv run python -m etl.refresh_activity --validate-only
uv run python -m etl.investigate_activity
```

The investigation command validates the matched files and reports daily counts,
the full-window peak, peak concentration, event drivers, checksum, and query
provenance. It omits account names from the concentration output. The aggregate
contains the latest weekly comparison and quality record.

For the four-week table and account-exclusion sensitivity check, run this Python
block from that checkout (Bash syntax):

```bash
uv run python - <<'PY'
from collections import Counter
from datetime import date, timedelta

from etl.refresh_activity import load_state
from pathlib import Path
from transform.recent_activity import period

state = load_state(Path("data"))
events = state["events"]
first = date.fromisoformat(state["coverage_start"])
for offset in range(0, 28, 7):
    start = first + timedelta(days=offset)
    end = start + timedelta(days=7)
    print(period(events, start.isoformat(), end.isoformat()))

for day in ("2026-10-13", "2026-10-14", "2026-10-20", "2026-10-21"):
    rows = [event for event in events if event["created_at"].startswith(day)]
    largest = max(Counter(event["actor_login"] for event in rows).values(), default=0)
    print(day, "events", len(rows), "largest account", largest, "excluding largest", len(rows) - largest)
PY
```

Later refreshes can change the available window and its peak. Recompute and
review the interpretation before updating this dated report.
