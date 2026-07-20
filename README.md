# Project ARGO

**A decision-intelligence platform that predicts open-source contributor churn from 547,434 real GitHub Archive events — and defends every number it produces.**

---

## Executive Summary

Maintainer attrition is the dominant failure mode of open-source infrastructure. A project does not die when its issue count spikes; it dies when the three people who understand the build system quietly stop showing up. That signal is buried in event streams nobody aggregates.

ARGO answers one concrete, falsifiable question:

> **Given a contributor's behaviour across a four-month observation window, will they go completely inactive in the following two months?**

Every number in this repository comes from `githubarchive.day.*` — real pushes, real pull requests, real reviews, from a curated cohort of ~24 production Python repositories (`python/cpython`, `pandas-dev/pandas`, `pytorch/pytorch`, `apache/airflow`, `huggingface/transformers`, …). There is no synthetic data. A model trained on generated events can only rediscover the rules its author wrote; this one cannot.

**Current state, measured not claimed:**

| | |
| --- | --- |
| Source events | 547,434 (2023-07-01 → 2024-01-01) |
| Eligible contributors | 3,033 (≥5 events across ≥3 distinct days) |
| Train / holdout | 2,426 / 607, split chronologically at 2023-09-06 |
| Holdout churn rate | 59.6% |
| Cross-validated ROC-AUC | 0.8137 (3-fold `TimeSeriesSplit`) |
| **Holdout ROC-AUC** | **0.7553** |
| Holdout precision / recall | 0.7704 / 0.6768 |
| Model | XGBoost — `max_depth=2, min_child_weight=5, n_estimators=400, lr=0.01, subsample=0.6` |
| dbt data tests | 7/7 passing |

**0.7553 is a modest number, and it is the honest one.** The 0.058 gap between cross-validation and holdout is real temporal generalisation loss, exposed deliberately by the chronological split. A random split reports a higher figure by leaking future cohorts into training. That higher figure is a lie.

---

## System Architecture (Data Flow)

```
Extraction              Warehouse                  Modelling                 Serving          Presentation
────────────────        ───────────────────        ────────────────────      ────────────     ───────────────
BigQuery                dbt + DuckDB           ─▶  XGBoost (16 features) ─▶  FastAPI      ─▶  Next.js 16
githubarchive.day.* ─▶  raw_github_events          SHAP TreeExplainer        /predict         React 19
  partition-pruned        ↓                        chronological holdout     /metrics         Tailwind v4
  column-pruned         ml_contributor_churn_      STL(period=7) anomalies   /customers       Recharts
  PyArrow zero-copy       training (3,033)                                   /governance
                        metric_contributor_
                          retention (21 cells)
                        metric_activity_
                          decomposition (184d)
                        meta_dbt_runs
```

**Stage 1 — Extraction.** A cost-bounded BigQuery job (`sql/bigquery/extract_python_contributor_events.sql`) reads `githubarchive.day.2023*` with `_TABLE_SUFFIX BETWEEN '0701' AND '1231'`. The wildcard is anchored to a year prefix so the dataset's logical views (`yesterday`, `today`) — whose schema mismatch raises a 400 — are excluded structurally. `SELECT *` is never used; the nested `payload` JSON dominates dataset size and is never referenced. Bots are filtered at source. The landing script prints `job.total_bytes_processed` so every run reports what it spent.

**Stage 2 — Landing.** `etl/land_github_data.py` moves results into DuckDB through Arrow with no intermediate serialisation: `job.to_arrow()` → `connection.register()` → `CREATE OR REPLACE TABLE`. No CSV round-trip, no pandas materialisation, no dtype coercion bugs. Both engines speak Arrow natively; the bytes are shared, not copied.

**Stage 3 — Transformation.** dbt materialises four marts. The training mart declares its observation and target windows once in a `bounds` CTE and enforces them as half-open `[start, end)` intervals. Seven schema tests gate the build.

**Stage 4 — Modelling.** `ml/train_churn.py` grid-searches 48 candidates over 3 forward-chaining folds, fits on the chronologically earlier cohort, and writes `churn_xgb.json`. `ml/evaluate_model.py` reproduces the identical split and emits a confusion matrix and SHAP summary to `frontend/public/assets/`. `ml/decompose_activity.py` runs STL on daily volume and flags 3σ residual outliers.

**Stage 5 — Serving.** FastAPI warms the model and SHAP explainer in its lifespan handler, so the first request pays no tree-traversal setup cost. An import-time assertion compares the Pydantic request schema against `FEATURE_COLUMNS` field-by-field; the app refuses to boot on drift.

**Stage 6 — Presentation.** Next.js renders four decoupled tabs. The threshold simulator sweeps the cached 607-row holdout client-side, recomputing a confusion matrix on every slider frame with zero round trips.

---

## Engineering Tradeoffs

### 1. DuckDB (columnar OLAP) over Postgres (row-store OLTP)

The default resume-driven answer is "put it in Postgres." That answer is wrong here, and the reasoning matters more than the choice.

**This workload has zero write paths.** ARGO never issues an `UPDATE`, never opens an interactive transaction, and never serves a point lookup by primary key. It executes wide analytical scans — `count(*) FILTER (WHERE event_category = ...)` across half a million rows, grouped by contributor. That is precisely the access pattern row-stores are worst at.

| Dimension | DuckDB | Postgres |
| --- | --- | --- |
| Storage layout | Columnar, compressed | Row-major heap pages |
| Scan of 6 of 13 columns | Reads 6 columns | Reads every column in every touched page |
| Execution | Vectorised, SIMD, multi-core by default | Tuple-at-a-time; parallelism opt-in, limited |
| Aggregation over 547k rows | 0.28s, single process | Index strategy, tuning, or a read replica |
| Operational surface | A file | Server process, WAL, vacuum, pooling, backups |
| Deployment | `COPY transform/argo.duckdb` into the image | Managed service, network hop, credential rotation |

**The concurrency objection is real and does not apply.** Postgres wins decisively on concurrent writers and transactional integrity. ARGO has exactly one writer — the ETL script, run offline — and N readers, all opening the file `read_only=True`. Paying a row-store's scan penalty plus operational overhead to buy MVCC guarantees that nothing in this system requires is a straight loss.

**The migration cost is not hypothetical.** The dbt layer leans on DuckDB-native constructs: `QUALIFY` for event deduplication, `arg_max` for last-seen repo attribution, `count(*) FILTER` for categorical rollups, `date_diff`/`to_days` anchored to window boundaries. Porting means rewriting every mart into window-function subqueries for no measured gain.

**When this decision flips:** the moment a write path appears — user annotations, feedback loops, multi-tenant state. The correct move then is Postgres for the OLTP surface *alongside* the columnar store, not migrating analytics into an engine that is bad at it.

### 2. Strict chronological train/test split over random sampling

**A random split on temporal data is a leak, and it is the most common quietly-fatal bug in applied ML.**

`train_test_split(shuffle=True)` scatters contributors from every era across both sets. The training set then contains contributors whose activity is *contemporaneous with* — and correlated with — the test set: the same release cycles, the same CVE scrambles, the same conference-season lulls, the same repository policy changes. The model learns period-specific artefacts and is graded on the period it memorised. The reported AUC measures the split, not the model.

ARGO sorts by `first_event_at` ascending and cuts 80/20:

```python
cutoff = int(len(frame) * _SPLIT_RATIO)
train = frame.iloc[:cutoff]
test = frame.iloc[cutoff:]
```

Training sees only contributors who joined before 2023-09-06. Evaluation happens exclusively on the newest cohort — one the model has no temporal adjacency to. **This reproduces the deployment condition:** in production the model always scores contributors who arrived after the training data was frozen.

Three reinforcing controls:

- Grid-search cross-validation uses `TimeSeriesSplit(n_splits=3)`, giving expanding-window forward chaining. Every validation fold is strictly later than the folds that trained it.
- `first_event_at` is projected for ordering only. `enforce_schema` restricts the matrix to `FEATURE_COLUMNS`, which excludes it — the split key cannot become a feature.
- `days_since_last_event` is anchored to `observation_end`, **never** to `max(created_at)`. Anchoring to the observed maximum makes recency non-comparable across contributors and smuggles future information into a feature that looks innocent. That single line separates a defensible model from a 0.99-AUC fantasy.

**The measured cost of honesty: CV 0.8137 → holdout 0.7553.** That 0.058 gap is the leak, quantified. It is reported, not hidden.

### 3. Two-stage risk ranking: top 50 by volume, then sort by model risk

`/api/v1/customers/risk` does not rank the cohort by churn probability. It takes the 50 highest-volume contributors, scores them live with XGBoost, and returns the 5 riskiest.

**Ranking the full cohort by probability alone produces garbage.** The most confidently-churning contributors are drive-bys: one commit, never seen again. The model is near-certain about them and correct — and the output is worthless, because a retention queue of people who contributed 3 events and left is not something any maintainer would action.

**Ranking by volume alone is equally useless.** It returns whoever is busiest, regardless of whether they are at any risk of leaving.

The intersection is the only actionable set. Live output:

```
sgugger       huggingface/transformers  1,619 events  27d idle  risk 40.0%
AA-Turner     python/cpython            1,254 events  14d idle  risk 30.2%
anijain2305   pytorch/pytorch           1,557 events  21d idle  risk 24.5%
adriangb      pydantic/pydantic         1,312 events   5d idle  risk  5.3%
LukasMasuch   streamlit/streamlit       1,590 events   4d idle  risk  4.6%
```

The same principle is enforced upstream in SQL. The training mart applies an eligibility floor:

```sql
having count(*) >= 5
    and count(distinct cast(o.created_at as date)) >= 3
```

Before that floor, the cohort was 54,613 contributors at a **91.6% churn rate** — dominated by drive-bys, trivially predictable, swamping the signal. The model scored holdout ROC-AUC 0.6620 with precision 0.9269, and that precision was an artefact of the base rate: predicting "everyone churns" scores similarly. After the floor: 3,033 contributors at 59.6%, ROC-AUC 0.7553, precision 0.7704.

**ROC-AUC rose while precision fell, and that is the correct trade.** The problem became genuinely hard, and the metrics became genuinely meaningful.

Scoring is performed live against the deployed artifact rather than read from a precomputed table, so the queue can never drift from the model actually serving predictions.

---

## Local Setup

Requires [uv](https://docs.astral.sh/uv/), Python 3.12, Node 20+, and a Google Cloud project with BigQuery enabled.

```bash
uv sync
npm --prefix frontend install
```

### Pipeline (strictly sequential — each step fails loudly without its predecessor)

```bash
# 1. Authenticate against BigQuery
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<your-project-id>

# 2. Extract real GitHub Archive events, land via zero-copy Arrow
uv run python etl/land_github_data.py

# 3. Build and test the warehouse
cd transform && uv run dbt build && cd ..

# 4. Capture dbt run metadata for the governance panel
uv run python -m etl.ingest_dbt_artifacts

# 5. Train on the chronologically earlier cohort
uv run python -m ml.train_churn

# 6. Evaluate on the pure temporal holdout; emit SHAP + confusion matrix PNGs
uv run python -m ml.evaluate_model

# 7. STL-decompose daily activity and flag 3-sigma anomalies
uv run python -m ml.decompose_activity
```

### Serve

```bash
uv run uvicorn api.main:app --reload      # http://127.0.0.1:8000/docs
npm --prefix frontend run dev             # http://localhost:3000
```

### Container

```bash
docker build -t argo-api .
docker run -d -p 8000:8000 --name argo-backend argo-api
```

The LLM narrative endpoint requires `NVIDIA_API_KEY` in a git-ignored `.env`. Everything else runs without credentials once step 2 has populated the warehouse.

---

## API Surface

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness probe |
| GET | `/api/v1/metrics/executive` | Active contributors (30d), PR/issue throughput (7d), retention |
| GET | `/api/v1/metrics/trend` | Monthly active contributors, 6 complete months |
| GET | `/api/v1/metrics/contributors/sparkline` | Trailing 12 complete weeks |
| GET | `/api/v1/metrics/throughput/sparkline` | Trailing 12 complete weeks |
| GET | `/api/v1/metrics/retention/sparkline` | Week-over-week retention |
| GET | `/api/v1/metrics/activity/decomposition` | STL trend/seasonal/residual + flagged anomalies |
| GET | `/api/v1/metrics/governance/health` | dbt test results, build times, row counts, source freshness |
| GET | `/api/v1/customers/risk` | Two-stage ranked retention queue |
| POST | `/api/v1/predict/churn` | Probability, log-odds, 16 SHAP contributions, top 3 factors |
| GET | `/api/v1/predict/simulate/threshold` | Scored holdout for client-side threshold sweeping |
| GET | `/api/v1/intelligence/summary` | LLM executive narrative |

---

## Notable Findings

**STL recovered the US holiday calendar from raw event volume.** Decomposing daily activity with `period=7` and flagging 3σ residuals — after weekly seasonality and trend are removed — surfaces five days across 184:

```
2023-07-04  collapse  z=-3.95   US Independence Day
2023-09-05  collapse  z=-4.16
2023-10-18  collapse  z=-3.04
2023-11-24  collapse  z=-4.42   day after US Thanksgiving
2023-12-19  spike     z=+3.70
```

The two deepest collapses are US public holidays. No calendar was supplied to the model.

**Cohort retention is triangular by construction.** `metric_contributor_retention` emits a cell only where activity was observed:

```
Jul 2023  n=16,872  100% → 12.05% → 9.02% → 8.17% → 7.40% → 6.74%
Aug 2023  n=12,918  100% →  8.10% → 5.27% → 4.75% → 3.75%
Sep 2023  n=12,505  100% →  7.66% → 4.77% → 3.89%
Oct 2023  n=12,318  100% →  6.50% → 3.72%
Nov 2023  n=11,837  100% →  5.96%
Dec 2023  n=10,845  100%
```

Zero-filling the empty upper-right is the classic error: it reports "0% retained" for periods never observed, dragging every recent cohort's curve to the floor. Absent means unobserved, not churned.

---

## Repository Layout

```
sql/bigquery/     Cost-bounded extraction SQL + cohort/window design doc
etl/              BigQuery → Arrow → DuckDB landing; dbt artifact ingestion
transform/        dbt project (source, marts) + argo.duckdb
ml/               Feature contract, training, temporal evaluation, SHAP, STL
api/              FastAPI routers, lifespan warm-up, drift assertion
frontend/         Next.js command suite
docs/             BI architecture specifications
```

---

## Known Limitations

- **607 holdout rows.** A ±0.02 ROC-AUC swing is inside sampling noise. Do not quote 0.7553 as precise; widening the repo cohort or observation window is the only way to shrink that error bar.
- **Hyperparameter search has converged.** Two successive grid expansions moved holdout AUC by −0.001. Remaining headroom is in the data, not the tuning.
- **"Preview outreach draft" is cosmetic and labelled as such.** The button renders a toast; no LLM call fires and no message is sent.
- **`metric_activity_decomposition` is a Python-side table.** `dbt build` will not rebuild it — `decompose_activity.py` must run after every landing.

---

## License

[MIT](LICENSE).
