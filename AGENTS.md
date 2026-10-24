# AGENTS.md

Permanent engineering conventions for Project Argo. Keep this file short; it
records rules that outlive any single task.

## Environment

- Python **3.12**, managed with **uv**. Never use system `pip`.
- `uv sync` installs from `uv.lock`; commit the lockfile with any dependency change.
- Add dependencies with `uv add <pkg>` (runtime) or `uv add --dev <pkg>` (tooling).

## Commands

| Task            | Command                          |
| --------------- | -------------------------------- |
| Install         | `uv sync`                        |
| Lint            | `uv run ruff check .`            |
| Format          | `uv run ruff format .`           |
| Test            | `uv run pytest`                  |
| Enable hooks    | `uv run pre-commit install`      |

## Conventions

- **Lean by default.** Create a directory, config, or dependency only when the
  first implementation needs it. No placeholders or speculative files.
- **Layers depend downward only:** `generator → warehouse → transform → serve →
  present`. No upstream imports.
- **Formatting/linting is enforced** by Ruff (Python) and SQLFluff
  (DuckDB dialect, dbt templater). Fix, don't suppress.
- **SQL/dbt:** models are `snake_case`; facts `fact_*`, dimensions `dim_*`.
  Every metric is defined once, in the semantic layer.
- **Secrets** live in `.env` (git-ignored) and are read via config, never
  hardcoded. Public demos may use documented public datasets; record their source
  and observation dates. Synthetic test fixtures must be labelled.
- **Commits** follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).
  CI (Ruff) must pass before merge.

## Decisions

Record an ADR under `docs/decisions/` only for a real, hard-to-reverse choice —
not routine work.

## Analytics Tracking - Mixpanel

Use Mixpanel for website usage analytics; keep it separate from the GitHub
contributor dataset. Read this section and docs/mixpanel-tracking.md before
changing tracking. Reuse existing events and the shared helper.

- Platform: Next.js / React web; mixpanel-browser ^2.84.0, client-side; no CDP.
- Token: NEXT_PUBLIC_MIXPANEL_TOKEN in Vercel production configuration or
  frontend/.env.local. Never commit tokens or API secrets.
- Initialization: frontend/src/lib/analytics.ts; SDK loads once after explicit
  consent. frontend/src/components/AnalyticsConsent.tsx supplies consent controls.
  DNT/GPC override acceptance. Preserve withdrawal and blocked-storage behavior.
- Identity: anonymous visitors only; no login/signup, identify calls or profiles.
  reset occurs on withdrawal. If authentication is added, identify only a stable
  internal ID after authentication and reset on logout/account switching.

| Event | Trigger | Custom properties | Location |
| --- | --- | --- | --- |
| dashboard_viewed | First view after consent per page load | platform: web | frontend/src/lib/analytics.ts |
| prediction_completed | Successful visitor-initiated prediction response | platform: web; prediction_source: manual or preset | frontend/src/components/ChurnWidget.tsx through analytics.ts |

Name new events/properties in snake_case and reuse the shared helper. Track
successful outcomes, deduplicate events, document new events here and verify
arrival in Live View. Keep numeric properties numeric. Do not collect contributor
identities, prediction inputs/outputs, form text, URL parameters or PII. Keep
autocapture, automatic pageviews, session replay and IP enrichment disabled.
Do not add another analytics SDK without user instruction. Test with
`cd frontend && node --test tests/analytics.test.mjs`.
