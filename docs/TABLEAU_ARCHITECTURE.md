# Tableau Architecture

Narrative layer for executive presentation. Where Power BI is the live
operational cockpit, Tableau Stories are the guided, board-ready arc: three
sequenced stories that walk from user behaviour to predictable revenue.

## Data connection

Tableau connects to `transform/argo.duckdb` via the **DuckDB JDBC driver** (or a
Parquet export of the marts for a portable `.twbx`). Sources: the `fact_*` and
`dim_*` tables for detail, the `metric_*` tables for pre-aggregated trends, and a
`churn_scores` extract (per-user probability from the `/predict/churn` model) for
Story 3. Extract mode is preferred for a self-contained presentation file.

## Story structure

Each Story is a sequence of caption-titled story points, every point backed by
one dashboard. Format: **16:9**, one takeaway per point, consistent color legend
for `subscription_plan` and `event_source` across all three stories.

---

## Story 1 — The User Journey (Visitor to Retention)

How a signup becomes a retained, activated user.

| Point | Caption | Backing viz | Source |
| --- | --- | --- | --- |
| 1 | "Where users enter" | Acquisition events by type | `fact_events` where `event_source = 'acquisition'` |
| 2 | "Do they activate?" | Activation funnel (registered → first actions) | `fact_events` where `event_source = 'activation'` |
| 3 | "How they engage" | Sessions/user, avg `duration_seconds` by `platform` | `fact_sessions` |
| 4 | "Which features stick" | Feature adoption by `feature_name` | `fact_feature_usage` |
| 5 | "Do they come back" | D1/D7/D30 retention heatmap by cohort | `metric_retention_cohorts` |

**Takeaway:** the activation-to-retention conversion and the feature usage that
separates retained from churned users.

---

## Story 2 — The Growth Story (Acquisition to Expansion)

The compounding loop from new users to expanding accounts.

| Point | Caption | Backing viz | Source |
| --- | --- | --- | --- |
| 1 | "New users over time" | Daily/weekly new registrations | `dim_users[first_seen_at]` |
| 2 | "Active-user momentum" | DAU / WAU / MAU trend, stickiness | `metric_active_users` |
| 3 | "Free to paid" | Trial → subscription conversion funnel | `fact_subscriptions[subscription_action]` |
| 4 | "Plan mix shift" | Accounts and revenue by `subscription_plan` | `dim_accounts`, `metric_mrr` |
| 5 | "Expansion vs contraction" | Upgrades/downgrades and cancellations | `fact_subscriptions` |

**Takeaway:** the growth engine — where users come from, how they convert, and
whether accounts expand or contract.

---

## Story 3 — The Predictable Revenue Story (Revenue at Risk)

Fusing the XGBoost churn model with revenue to quantify what is at stake.

| Point | Caption | Backing viz | Source |
| --- | --- | --- | --- |
| 1 | "Recurring revenue base" | MRR / ARR trend | `metric_mrr` |
| 2 | "Who is likely to churn" | Distribution of churn probability | `churn_scores` (model output) |
| 3 | "Revenue at risk" | Plan price × churn probability, summed by plan | `churn_scores` × `dim_accounts[subscription_plan]` |
| 4 | "Risk concentration" | Revenue-at-risk by region / plan / team size | `churn_scores` × `dim_users`, `dim_accounts` |
| 5 | "Act on it" | Prioritized save-list: highest expected-loss accounts | `churn_scores` ranked by `probability × plan_price` |

**Revenue-at-Risk measure:** `SUM(churn_probability × monthly_plan_price)` — the
expected monthly MRR loss, turning a model score into a board-level dollar figure
and a prioritized retention action list.

**Takeaway:** revenue is not just reported, it is *predicted* — the platform
closes the Observation → Insight → Decision → Action loop by naming the accounts
whose churn would cost the most.
