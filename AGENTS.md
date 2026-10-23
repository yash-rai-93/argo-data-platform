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
