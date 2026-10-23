# Redeploying Argo under yash-rai-93

This deployment serves a documented historical public GitHub Archive snapshot.
The study spans [2023-07-01, 2024-01-01), with features ending at 2023-11-01.
It is not a live event feed. Synthetic fixtures are for tests; published model
results must identify their real data source and evaluation window.

The warehouse and both trained models are committed. First validate and deploy
that matched set; BigQuery access and historical reproduction are separate work.
Do not regenerate data just to change hosting accounts.

## Repository and deployment settings

| Item | Setting |
| --- | --- |
| GitHub | https://github.com/yash-rai-93/argo-data-platform |
| Production branch | main |
| Backend | Render Docker web service, configured in render.yaml |
| Backend root / Dockerfile | Repository root / ./Dockerfile |
| Dashboard | Vercel Next.js project; root directory frontend |
| Vercel install / build | npm ci / npm run build |
| Node.js | 22, matching frontend CI |
| Container package | ghcr.io/yash-rai-93/argo-backend |
| Backend health check | /health |
| Runtime GCP credentials | None |
| Persistent database service/disk | None; warehouse is bundled and read-only |

Import the repository with the new account's GitHub integrations. Render should
deploy after CI checks pass. The blueprint requests the Free plan in Singapore;
verify availability and current resource limits before creating the service.
Measure startup and memory rather than treating older README measurements as a
guarantee. Free instances sleep after inactivity.

Once Render returns an HTTPS origin, set Vercel's NEXT_PUBLIC_API_URL to that
exact origin, with no trailing slash or /api/v1. Configure Production and Preview,
then build a new deployment. This value is compiled into browser JavaScript.

Record actual new URLs in the README only after live checks pass. Do not reuse
the previous account's hostnames or assume the proposed service name is available.

## Configuration

Copy .env.example to .env for local work, and use uv run --env-file .env.
The file is ignored by Git and Docker. For hosted services, configure environment
variables in the platform's settings.

| Variable | Where | Purpose |
| --- | --- | --- |
| GOOGLE_CLOUD_PROJECT | Extraction only | Explicit project to run/bill BigQuery jobs |
| BIGQUERY_LOCATION | Extraction only | Defaults to US; verify source location first |
| BIGQUERY_MAX_BYTES_BILLED | Extraction only | Required positive integer for an actual extraction |
| NEXT_PUBLIC_API_URL | Vercel frontend | Public backend origin; rebuild after a change |
| OPENROUTER_API_KEY | Backend, optional | Provider credential |
| OPENROUTER_MODEL | Backend, optional | Explicit model identifier; check availability/pricing first |

With either OpenRouter setting absent, the API summarizes the actual stored
contributor metrics without making a provider request. No paid model is needed
for the first deployment. Never put a provider key in a NEXT_PUBLIC_ variable.

Keep /app and /home/user in the Docker image. Python resolves the warehouse and
model paths relative to source files, so those paths need no account migration.
Keep transform/argo.duckdb and the ml/models artifact filenames stable.

## GCP setup for historical reproduction

1. Select/create a project Yash controls and confirm its billing arrangement.
2. Verify the githubarchive source location and choose the matching job location.
3. Enable BigQuery and BigQuery Storage APIs.
4. For GitHub builds, enable the IAM, IAM Credentials, and Security Token Service
   APIs required for Workload Identity Federation.
5. Create an argo-etl service account with BigQuery Job User on the query project
   and BigQuery Read Session User for Storage Read downloads. Verify necessary
   source/result read access; grant dataset-scoped permissions only as needed.
6. Configure a GitHub OIDC identity pool/provider and service-account
   impersonation. Restrict trust to this exact repository and refs/heads/main;
   prefer immutable repository/owner IDs for identity conditions.
7. Add these GitHub Actions repository variables:

| Repository variable | Value |
| --- | --- |
| GCP_PROJECT_ID | Actual project ID |
| GCP_WORKLOAD_IDENTITY_PROVIDER | Full projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL/providers/PROVIDER resource name |
| GCP_ETL_SERVICE_ACCOUNT | argo-etl@PROJECT_ID.iam.gserviceaccount.com |

Use the Google authentication action's documented federation setup. Do not
download/upload a long-lived service-account key for this workflow. Temporary
gha-creds-*.json files are excluded from Git, Docker context, and artifact uploads.

The source githubarchive.day.2023* is a public upstream dataset; do not replace
that path with the new project ID. The extractor does not need a permanent
destination BigQuery dataset or GCS bucket: results land directly in DuckDB.

For an interactive local extraction, configure Google ADC and its quota project
for the selected account. A gcloud CLI login alone does not configure ADC.

## Cost-bounded extraction

First estimate the scan, without replacing the existing warehouse:

```bash
uv sync --frozen
uv run --env-file .env python -m etl.land_github_data --dry-run
```

Review the reported bytes and the project's remaining allowance/pricing. Set a
positive BIGQUERY_MAX_BYTES_BILLED in .env, or pass --maximum-bytes-billed with the
reviewed value. A real extraction refuses to start without the cap:

```bash
uv run --env-file .env python -m etl.land_github_data
```

Budget notifications do not stop queries. Use the per-query bytes-billed limit
as the execution guardrail, alongside suitable query quotas. Do not assume a
filtered query is free without checking its estimate.

In GitHub Actions, run “Rebuild historical data” from main:
- dry-run is the default and only estimates the scan.
- rebuild requires a positive maximum_bytes_billed input.
- No query or retraining happens on ordinary pushes or pull requests.

The workflow builds dbt models/tests, ingests governance artifacts, trains both
models, generates evaluation charts and decomposition, and smoke-tests the API.
It uploads a matched artifact set plus source-commit/checksum metadata for seven
days. It does not commit or deploy newly trained artifacts automatically.

Review results before replacing the committed warehouse, both models and
parameter files, and associated charts together. Keep the existing time windows
and allow-list for reproduction; a new study period is a separate modelling
change. Historical registry entries and scores are not new measurements.

## Verification and release

CI checks Python format/lint/tests, dbt build/leakage tests, SQL lint, frontend
lint/build, and the actual backend container. None needs Google credentials.

The container smoke check exercises every current GET endpoint, valid
16-feature inference, survival/SHAP output, and invalid-request rejection.
Model warm-up currently logs failures and continues, so /health alone does not
establish that inference works.

Local Docker verification:

```bash
docker build -t argo-backend .
docker run --rm -p 7860:7860 argo-backend
# In another terminal:
uv run python -m api.smoke_test
```

Hosted API verification:

```bash
uv run python -m api.smoke_test --base-url https://YOUR_NEW_API_ORIGIN
```

Check the real dashboard against the new API, including SHAP, survival curves,
PDF export, and one idle-to-warm startup. Confirm source dates, links, and
summary text. Record deployed commit, actual URLs, and artifact checksums.

The package workflow tests its image before publishing. Use manual dispatch
for the first package check, or create a new release tag at the verified commit.
The migrated v3.0.0 tag retains old source and predates these deployment fixes.

For rollback, redeploy the prior application commit with its complete matched
warehouse/model/chart set. Rebuild Vercel if the backend origin changes. Keep
previous services intact until the new deployment passes. No force-push is
needed for deployment or rollback.

## Official references

- [Render Blueprint fields](https://render.com/docs/blueprint-spec)
- [Render free-service limits](https://render.com/docs/free)
- [Vercel environment settings](https://vercel.com/docs/environment-variables/managing-environment-variables)
- [BigQuery query-cost controls](https://docs.cloud.google.com/bigquery/docs/best-practices-costs)
- [Google GitHub authentication action](https://github.com/google-github-actions/auth)
