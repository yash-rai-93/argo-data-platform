"""Shared FastAPI dependencies and query helpers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb

_DB_PATH = Path(__file__).resolve().parents[1] / "transform" / "argo.duckdb"


def get_db() -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield a read-only warehouse connection and close it afterwards."""
    connection = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        yield connection
    finally:
        connection.close()


def fetch_executive_metrics(db: duckdb.DuckDBPyConnection) -> dict:
    """Return the headline GitHub cohort KPIs.

    All windows are anchored to max(created_at) in the warehouse, never
    current_date: the archive extract is a fixed historical window, so wall
    clock would return zeros.
    """
    active_contributors, pr_throughput, retention_rate = db.execute(
        """
        with bounds as (
            select max(created_at) as anchor from raw_github_events
        ),

        windows as (
            select
                anchor,
                anchor - interval 30 day as current_start,
                anchor - interval 60 day as prior_start,
                anchor - interval 7 day as week_start
            from bounds
        ),

        current_cohort as (
            select distinct e.actor_login
            from raw_github_events as e, windows as w
            where e.created_at >= w.current_start
        ),

        prior_cohort as (
            select distinct e.actor_login
            from raw_github_events as e, windows as w
            where e.created_at >= w.prior_start
                and e.created_at < w.current_start
        )

        select
            (select count(*) from current_cohort) as active_contributors,
            (
                select count(*)
                from raw_github_events as e, windows as w
                where e.created_at >= w.week_start
                    and e.event_category in ('pull_request', 'issue')
            ) as pr_throughput,
            coalesce(
                (
                    select count(*)
                    from prior_cohort as p
                    where p.actor_login in (select actor_login from current_cohort)
                ) / nullif(cast((select count(*) from prior_cohort) as double), 0),
                0
            ) as retention_rate
        """
    ).fetchone()
    return {
        "active_contributors": int(active_contributors),
        "pr_throughput": int(pr_throughput),
        "retention_rate": float(retention_rate),
    }
