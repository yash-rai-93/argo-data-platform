# Project Argo

**A product- and decision-intelligence platform that turns raw product events
into predicted, dollar-quantified business decisions.**

> Observation → Insight → Decision → Action → Impact.

Argo is an end-to-end analytics + ML system: it synthesizes a realistic SaaS
event stream, models it into a governed dimensional warehouse, trains a churn
model on leakage-free features, generates executive narratives with an LLM, and
serves it all through a typed API — the same architecture a product-analytics
company runs in production, built solo.

## Project status

| Layer | Status |
| --- | --- |
| Synthetic data pipeline | ✅ Built & tested (determinism, ordering, identity invariants) |
| dbt + DuckDB warehouse | ✅ Built & tested (star schema, schema tests, CI) |
| XGBoost churn model | ✅ Built & tested (leakage-free, ~0.97 ROC-AUC) |
| FastAPI serving layer | ✅ Built & smoke-tested (metrics, prediction, LLM) |
| Power BI / Tableau BI | 🚧 Architectural design phase (see [docs/](docs/)) |

The data pipeline, ML model, and API are implemented and tested end to end. The
BI dashboards are currently specified as architecture (data model, relationships,
dashboard/story layouts) and are the next build milestone.

## Core business problem

SaaS companies lose revenue to churn they see only after it happens. Argo closes
that gap: it unifies fragmented product events into governed metrics, predicts
which accounts will churn, and translates those predictions into **revenue at
risk** — a prioritized, dollar-ranked retention action list.

## System architecture

```
Synthetic events        Warehouse                 Intelligence            Serving        Presentation
─────────────────       ─────────────────         ──────────────────      ───────────    ─────────────
Python + Pydantic  ─▶   dbt + DuckDB         ─▶   XGBoost (churn)     ─▶   FastAPI    ─▶  Power BI
Faker, seeded,          staging → intermediate     NVIDIA Nemotron          /metrics       Tableau
lifecycle-aware         → marts → metrics          (LLM summaries)          /predict       (4 stories)
(6 event families)      (star schema, tested)                               /intelligence
```

**Flow:** a deterministic generator emits a canonical event stream → dbt builds a
Kimball star schema in DuckDB (facts, dimensions, semantic metric tables, all
data-tested) → an XGBoost classifier scores churn on point-in-time features → an
LLM turns the latest KPIs into an executive summary → FastAPI exposes metrics,
predictions, and narratives → BI layers (Power BI dashboards, Tableau stories)
consume the marts.

## Tech stack

| Layer | Tooling |
| --- | --- |
| Generation | Python 3.12, Pydantic, Faker (seeded, deterministic) |
| Warehouse | DuckDB, dbt (staging → intermediate → marts → metrics) |
| ML | scikit-learn, XGBoost |
| LLM | NVIDIA Nemotron via OpenAI-compatible client |
| Serving | FastAPI, Pydantic, Uvicorn |
| BI | Power BI, Tableau |
| Quality / CI | Ruff, pytest, SQLFluff, pre-commit, GitHub Actions |
| Tooling | uv |

## Key engineering decisions

- **Target-leakage prevention.** Churn features are strictly point-in-time: a
  `cutoff_date` 30 days before the data's end splits an **observation window**
  (features) from a **label window** (outcome). Removing the leak dropped ROC-AUC
  from a fantasy 0.9995 to an honest ~0.97 — the difference between a demo and a
  model you can defend.
- **Dimensional modeling.** A Kimball star schema (`fact_events`,
  `fact_sessions`, `fact_subscriptions`, `fact_feature_usage` conformed to
  `dim_users`, `dim_accounts`) keeps facts at a single grain and metrics defined
  once in a semantic layer — no metric drift across consumers.
- **Materialized tables for serving.** Staging/intermediate are views; marts and
  metrics are `+materialized: table`, so they stop re-reading raw JSON and the
  API resolves them read-only from any working directory.
- **Deterministic synthetic data.** A seeded, lifecycle-aware generator
  (Anonymous → Registered → Activated → Engaged → Churned/Retained) produces
  reproducible data with real funnel drop-off and strictly ordered timestamps —
  tested for determinism, identity persistence, and temporal ordering.
- **Tested transformations.** Every model carries dbt schema tests (uniqueness,
  not-null on keys); CI runs Ruff, pytest, SQLFluff, and `dbt build` on a freshly
  generated dataset.
- **Cached model loading.** The API loads the XGBoost artifact once via an
  LRU-cached loader, not per request.

## API surface

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness probe |
| GET | `/api/v1/metrics/executive` | Latest MRR, ARR, DAU |
| GET | `/api/v1/intelligence/summary` | LLM executive summary of current metrics |
| POST | `/api/v1/predict/churn` | Churn prediction + probability for a user |

## Local setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync                                   # environment from uv.lock

# 1. Generate the synthetic event feed
uv run argo-gen --users 1000 --days 180 --seed 42

# 2. Build and test the warehouse (from transform/)
cd transform
uv run dbt build --profiles-dir . --project-dir .
cd ..

# 3. Train the churn model
uv run python ml/train_churn.py

# 4. Serve the API
uv run uvicorn api.main:app --reload      # http://127.0.0.1:8000/docs

# 5. Smoke-test the endpoints (separate shell)
uv run python api/smoke_test.py
```

The LLM endpoint needs `NVIDIA_API_KEY` in a git-ignored `.env`. See
[AGENTS.md](AGENTS.md) for engineering conventions and
[docs/](docs/) for the BI architecture.

## Dashboard preview

> 🚧 **[GIF coming soon]** — Power BI dashboards (Executive Command Center,
> Product Intelligence, Customer Health, Revenue Intelligence) and Tableau
> stories are in the design phase. Layouts are specified in
> [docs/POWER_BI_ARCHITECTURE.md](docs/POWER_BI_ARCHITECTURE.md) and
> [docs/TABLEAU_ARCHITECTURE.md](docs/TABLEAU_ARCHITECTURE.md).

## License

[MIT](LICENSE).
