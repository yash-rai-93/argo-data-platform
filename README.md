# Project Argo

**A product- and decision-intelligence platform** that turns raw product events into
governed metrics, forecasts, and recommended actions — the analytics spine behind
retention, revenue, and growth decisions.

> Observation → Insight → Decision → Action → Impact.

## What it does

Argo models a SaaS business end to end: it ingests product-usage events, builds a
dimensional warehouse, publishes a governed semantic layer of KPIs (DAU/WAU/MAU,
MRR/ARR, NRR/GRR, retention, activation, churn), serves them through an API, and
surfaces them in BI dashboards and ML-driven predictions (churn, upsell, forecasting).

## Architecture

```
events ──▶ warehouse ──▶ transform ──▶ semantic ──▶ serve ──▶ present
(synthetic   (Postgres/    (dbt: staging  (governed    (FastAPI)  (BI + ML)
 generator)   Supabase)     → marts)       KPIs)
```

## Tech stack

| Layer      | Tooling                                   |
| ---------- | ----------------------------------------- |
| Warehouse  | PostgreSQL / Supabase, dimensional (Kimball) |
| Transform  | dbt (staging → marts → semantic)          |
| Serving    | FastAPI, Pydantic                         |
| ML         | scikit-learn, XGBoost, Prophet, SHAP      |
| BI         | Power BI, Tableau                         |
| Quality/CI | Ruff, pytest, SQLFluff, pre-commit, GitHub Actions |
| Tooling    | uv (Python 3.12)                          |

## Quickstart

```bash
uv sync                 # create the environment from uv.lock
uv run pre-commit install
uv run ruff check .     # lint
```

## Status

Foundation in place (tooling, CI, conventions). Data generator, warehouse, and
dbt models are the next milestone. See [AGENTS.md](AGENTS.md) for engineering
conventions.

## License

[MIT](LICENSE).
