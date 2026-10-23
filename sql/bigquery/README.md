# Historical GitHub Archive extraction

The query reads githubarchive.day.2023* for 2023-07-01 through 2023-12-31.
It selects event identifiers/types, actor/repository names, and timestamps,
filters bots, and scopes activity to 24 Python repositories. It does not read
the large payload column.

The upstream path belongs to the public dataset, not the previous project
owner. Set GOOGLE_CLOUD_PROJECT to the project running the job; keep the public
source path unchanged.

Features use [2023-07-01, 2023-11-01); labels use
[2023-11-01, 2024-01-01). The downstream dbt mart requires at least five events
across three distinct observation days. Its leakage assertion verifies the
feature-window boundary.

## Extract

Follow [the deployment runbook](../../docs/DEPLOYMENT.md) to configure ADC or
GitHub OIDC authentication. Verify the source location before running.

```bash
uv run --env-file .env python -m etl.land_github_data --dry-run
```

Review the estimated bytes, then set a positive BIGQUERY_MAX_BYTES_BILLED or
pass --maximum-bytes-billed explicitly:

```bash
uv run --env-file .env python -m etl.land_github_data
```

A dry run does not download data or replace the warehouse. An actual extraction
refuses to run without a cap; an empty result cannot overwrite existing data.
The API never queries BigQuery at request time.

The extractor lands results directly in transform/argo.duckdb. A permanent
BigQuery destination table is not required. After changing raw events, rebuild
dbt marts, governance metadata, both models, charts, and decomposition as one
matched artifact set; do not deploy a new warehouse with old models.
