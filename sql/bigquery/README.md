# Real-Data Layer: GitHub Contributor Churn (BigQuery → DuckDB)

This directory holds the BigQuery extraction that replaces Argo's synthetic
Faker data with **real GitHub Archive events**. It reframes the churn model
from a fictional SaaS to a genuine, studied problem:

> **Will an active open-source contributor go inactive in the next 2 months,
> and what behaviour predicts it?** (open-source sustainability / maintainer burnout)

## The cohort (and why it's defensible)

- **Scope:** the top ~24 Python open-source projects, spanning web
  (Django, Flask, FastAPI), data (pandas, NumPy, SciPy), ML
  (PyTorch, transformers, scikit-learn, Keras), and infra (Airflow, Ansible).
- **Why an allow-list, not "all Python":** GitHub Archive events carry no
  language field. A curated list of well-known Python repos is cheap to scan,
  easy to justify in an interview, and gives a real, high-signal contributor
  population. (A future version can join `bigquery-public-data.github_repos`
  to detect language programmatically.)
- **Bots removed:** `dependabot`, `github-actions`, `renovate`, etc. are
  filtered out so the cohort is real humans — this is real data cleaning, not
  cosmetic.

## The churn definition (mirrors the existing leakage-free split)

The window below reuses the exact observation/label pattern already built in
`ml/feature_extractor.py`:

| Phase | Window | Use |
|---|---|---|
| **Observation** | 2023-07-01 → 2023-10-31 (4 months) | compute contributor features |
| **Label** | 2023-11-01 → 2023-12-31 (2 months) | decide churned vs. retained |

- **Eligible contributor:** ≥ 1 non-bot event on an allow-listed repo during
  the observation window.
- **`is_churned = 1`** if that contributor has **zero** events in the label
  window; else `0`.
- Features are computed only from the observation window, so no label leakage.

The SQL extracts the full 6-month window in one pass; the observation/label
split is applied downstream in dbt/DuckDB.

## Features this enables (built downstream, from the landed events)

Per contributor, from the observation window: event counts by category
(`commit`, `pull_request`, `issue`, `comment`, `engagement`, `release`),
total events, distinct repos touched, distinct active days, tenure
(first event → cutoff), recency (last event → cutoff), and weekend-activity
ratio.

## How to run (once your GCP project + BigQuery are set up)

1. Open the BigQuery console, paste `extract_python_contributor_events.sql`.
2. **Check cost first:** Query settings → it shows estimated bytes scanned
   (or run `bq query --dry_run --use_legacy_sql=false < extract_...sql`).
   Only 5 small columns are read, so this stays well inside the 1 TB/month
   free tier.
3. Run it. Save results to a table (e.g. `argo.python_contributor_events`).
4. Land it in the local DuckDB warehouse for the rest of the pipeline
   (dbt marts → feature extractor → XGBoost + SHAP → API → dashboard).
   A landing script is the next step.

## Cost guardrail

Never `select *` here — the `payload` column is a large JSON blob and scanning
it across the window is what would blow the free tier. This query deliberately
avoids it. Any future payload-derived feature (commit counts, PR merge status)
should be added in a **separate, narrowly-scoped** query.
