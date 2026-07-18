# Power BI Architecture

How the Argo DuckDB warehouse is surfaced in Power BI: connectivity, the
semantic model, and the four core dashboards.

## 1. Connectivity & storage mode

Power BI has no first-party DuckDB connector. Argo connects through the
**DuckDB ODBC driver**, exposing the `main` schema of `transform/argo.duckdb`.

| Option | When to use | Trade-off |
| --- | --- | --- |
| **DirectQuery (recommended)** | Live reporting straight off the warehouse | No data copy; dashboards reflect the latest `dbt build`. Requires the ODBC driver on every gateway host. |
| Import | Offline / published demo (e.g. Power BI Service without a gateway) | Fast visuals, but a stale snapshot until refresh. |

**Recommendation: DirectQuery.** The marts and metrics are materialized as
physical **tables** (`marts`, `metrics` → `+materialized: table`), so DirectQuery
folds cleanly to columnar scans without re-reading the raw JSONL. Point Power BI
at the pre-aggregated `metric_*` tables for KPI cards and at the `fact_*` tables
for exploratory drill-down.

## 2. Logical data model

| DuckDB table | Power BI role | Grain |
| --- | --- | --- |
| `dim_users` | Dimension | one row per `user_id` |
| `dim_accounts` | Dimension | one row per `account_id` |
| `fact_events` | Fact | one row per event |
| `fact_sessions` | Fact | one row per session |
| `fact_feature_usage` | Fact | one row per feature-touch event |
| `fact_subscriptions` | Fact | one row per monetization action |
| `metric_active_users` | Aggregate | one row per day (DAU/WAU/MAU) |
| `metric_mrr` | Aggregate | one row per month (MRR/ARR) |
| `metric_retention_cohorts` | Aggregate | one row per signup-day cohort |

> **Gap to close:** there is no `dim_date` yet. Power BI time intelligence
> (YoY, rolling averages, fiscal calendars) needs a dedicated date dimension.
> Add `dim_date` to the warehouse and relate every fact's timestamp to it before
> building time-based measures; until then, use the pre-computed `metric_*`
> tables for trends.

## 3. Star schema relationships

Single-direction filters flow from dimensions to facts. All relationships are
one-to-many (dimension → fact) on the natural keys.

```
                 dim_accounts (account_id)
                        | 1
                        | *
   +--------------------+--------------------+
   |          |          |                   |
fact_events fact_sessions fact_subscriptions fact_feature_usage
   |          |                              |
   | *        | *                            | *
   +----------+---------- 1 -----------------+
                 dim_users (user_id)
```

| From (dimension) | To (fact) | Key | Cardinality | Cross-filter |
| --- | --- | --- | --- | --- |
| `dim_users` | `fact_events` | `user_id` | 1 → * | Single |
| `dim_users` | `fact_sessions` | `user_id` | 1 → * | Single |
| `dim_users` | `fact_subscriptions` | `user_id` | 1 → * | Single |
| `dim_users` | `fact_feature_usage` | `user_id` | 1 → * | Single |
| `dim_accounts` | `fact_events` | `account_id` | 1 → * | Single |
| `dim_accounts` | `fact_sessions` | `account_id` | 1 → * | Single |
| `dim_accounts` | `fact_subscriptions` | `account_id` | 1 → * | Single |
| `dim_accounts` | `fact_feature_usage` | `account_id` | 1 → * | Single |

The `metric_*` tables stand alone (report-level KPI sources) and are not related
into the star, avoiding ambiguous filter paths.

## 4. Core dashboards

### 4.1 Executive Command Center
Board-level health at a glance.
- **KPI row:** MRR, ARR (`metric_mrr`); DAU / WAU / MAU and stickiness = DAU/MAU (`metric_active_users`).
- **Trend:** active users over time; MRR by month.
- **Retention heatmap:** `metric_retention_cohorts` (cohort × day 1/7/30).
- **Slicers:** `dim_users[subscription_plan]`, `dim_users[region]`.

### 4.2 Product Intelligence
What users actually do.
- **Feature adoption:** count of `fact_feature_usage` by `feature_name`; unique users per feature.
- **Session engagement:** avg `duration_seconds` and `event_count` from `fact_sessions`, split by `platform` / `device_type`.
- **Event funnel:** `fact_events` filtered by `event_source` (acquisition → activation → engagement).
- **Slicers:** `feature_name`, `dim_users[platform]`.

### 4.3 Customer Health
Account-level retention and risk.
- **Account roster:** `dim_accounts` with `team_size`, `last_active_at`, `subscription_plan`.
- **Activity recency:** days since `last_active_at`; flag dormant accounts.
- **Churn scoring:** surface the model's churn probability (from the `/predict/churn` API) per account for a health-score column.
- **Slicers:** `subscription_plan`, `team_size` band.

### 4.4 Revenue Intelligence
Monetization and expansion.
- **MRR / ARR trend:** `metric_mrr` by `revenue_month`.
- **Plan mix:** revenue and account counts by `subscription_plan` (`dim_accounts`, `fact_subscriptions`).
- **Subscription actions:** `fact_subscriptions[subscription_action]` funnel (trial_started → subscription_started → payment_completed; cancellations and downgrades as contraction).
- **Slicers:** `subscription_plan`, `dim_users[region]`.
