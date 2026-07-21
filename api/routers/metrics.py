"""Executive metrics endpoints."""

from __future__ import annotations

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends

from api.deps import fetch_executive_metrics, get_db

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

DbConn = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]


@router.get("/executive")
def executive_metrics(db: DbConn) -> dict:
    """Return active contributors (30d), PR/issue throughput (7d), retention."""
    return fetch_executive_metrics(db)


@router.get("/trend")
def contributor_trend(db: DbConn) -> list[dict]:
    """Return the last six complete months of monthly active contributors."""
    rows = db.execute(
        """
        with monthly as (
            select
                date_trunc('month', created_at) as m,
                count(distinct actor_login) as contributors
            from raw_github_events
            where created_at < date_trunc(
                'month', (select max(created_at) from raw_github_events)
            )
            group by date_trunc('month', created_at)
        )

        select strftime(m, '%b') as name, contributors
        from monthly
        order by m desc
        limit 6
        """
    ).fetchall()
    return [{"name": name, "value": int(value)} for name, value in reversed(rows)]


@router.get("/contributors/sparkline")
def contributors_sparkline(db: DbConn) -> list[int]:
    """Return the trailing twelve weeks of weekly distinct contributors."""
    rows = db.execute(
        """
        select count(distinct actor_login) as contributors
        from raw_github_events
        where created_at >= (
            select max(created_at) - interval 84 day from raw_github_events
        )
            -- Drop the trailing partial week; it always reads as a collapse.
            and date_trunc('week', created_at) < (
                select date_trunc('week', max(created_at)) from raw_github_events
            )
        group by date_trunc('week', created_at)
        order by date_trunc('week', created_at) asc
        """
    ).fetchall()
    return [int(contributors) for (contributors,) in rows]


@router.get("/throughput/sparkline")
def throughput_sparkline(db: DbConn) -> list[int]:
    """Return the trailing twelve weeks of weekly PR and issue event counts."""
    rows = db.execute(
        """
        select count(*) as throughput
        from raw_github_events
        where created_at >= (
            select max(created_at) - interval 84 day from raw_github_events
        )
            and event_category in ('pull_request', 'issue')
            -- Drop the trailing partial week; it always reads as a collapse.
            and date_trunc('week', created_at) < (
                select date_trunc('week', max(created_at)) from raw_github_events
            )
        group by date_trunc('week', created_at)
        order by date_trunc('week', created_at) asc
        """
    ).fetchall()
    return [int(throughput) for (throughput,) in rows]


@router.get("/retention/sparkline")
def retention_sparkline(db: DbConn) -> list[float]:
    """Return week-over-week contributor retention across the trailing quarter.

    Each point is the share of the prior week's contributors who returned in
    the following week. Computed with a self-join on consecutive week buckets.
    """
    rows = db.execute(
        """
        with weekly as (
            select distinct
                date_trunc('week', created_at) as w,
                actor_login
            from raw_github_events
            where created_at >= (
                select max(created_at) - interval 91 day from raw_github_events
            )
        ),

        sizes as (
            -- Exclude the final two buckets: the last week is partial, and the
            -- second-to-last has no complete successor to be retained into.
            select w, count(*) as cohort_size
            from weekly
            where w < (
                select date_trunc('week', max(created_at)) - interval 7 day
                from raw_github_events
            )
            group by w
        ),

        returned as (
            select
                prev.w as w,
                count(*) as retained
            from weekly as prev
            inner join weekly as nxt
                on prev.actor_login = nxt.actor_login
                and nxt.w = prev.w + interval 7 day
            group by prev.w
        )

        select coalesce(r.retained / cast(s.cohort_size as double), 0) as rate
        from sizes as s
        left join returned as r on s.w = r.w
        order by s.w asc
        """
    ).fetchall()
    return [round(float(rate), 4) for (rate,) in rows]


@router.get("/activity/decomposition")
def activity_decomposition(db: DbConn) -> dict:
    """Return the STL decomposition of daily activity plus flagged anomalies.

    Populated by ml/decompose_activity.py. Anomalies are residual outliers
    beyond three sigma, so weekly seasonality and the underlying trend are
    already removed: a flagged day is one the calendar cannot explain.
    """
    rows = db.execute(
        """
        select
            activity_date,
            observed,
            trend,
            seasonal,
            residual,
            residual_zscore,
            is_anomaly
        from metric_activity_decomposition
        order by activity_date asc
        """
    ).fetchall()

    series = [
        {
            "date": date.isoformat(),
            "observed": int(observed),
            "trend": round(float(trend), 2),
            "seasonal": round(float(seasonal), 2),
            "residual": round(float(residual), 2),
            "zscore": round(float(zscore), 2),
            "is_anomaly": bool(flag),
        }
        for date, observed, trend, seasonal, residual, zscore, flag in rows
    ]
    return {
        "series": series,
        "anomalies": [point for point in series if point["is_anomaly"]],
    }


@router.get("/governance/health")
def governance_health(db: DbConn) -> dict:
    """Return dbt build health, test results, and warehouse freshness.

    Sourced from main.meta_dbt_runs, populated by etl/ingest_dbt_artifacts.py
    straight out of dbt's own run_results.json. Nothing here is hand-maintained,
    so it cannot drift from what the pipeline actually did.
    """
    latest = db.execute(
        """
        select invocation_id, run_at, dbt_version, run_elapsed_time
        from meta_dbt_runs
        order by run_at desc
        limit 1
        """
    ).fetchone()

    if latest is None:
        return {"status": "unknown", "detail": "No dbt run has been ingested."}

    invocation_id, run_at, dbt_version, elapsed = latest

    nodes = db.execute(
        """
        select node_name, resource_type, materialization, status,
               execution_time, failures, row_count, file_path
        from meta_dbt_runs
        where invocation_id = ?
        order by resource_type asc, node_name asc
        """,
        [invocation_id],
    ).fetchall()

    tests = [
        {
            "name": name,
            "status": status,
            "failures": int(failures),
            "execution_time": round(float(exec_time), 4),
        }
        for name, rtype, _mat, status, exec_time, failures, _rows, _path in nodes
        if rtype == "test"
    ]
    models = [
        {
            "name": name,
            "resource_type": rtype,
            "materialization": mat,
            "status": status,
            "execution_time": round(float(exec_time), 4),
            "row_count": int(rows),
            "file_path": path,
        }
        for name, rtype, mat, status, exec_time, _failures, rows, path in nodes
        if rtype in ("model", "seed")
    ]

    source_min, source_max, source_rows = db.execute(
        """
        select min(created_at), max(created_at), count(*)
        from raw_github_events
        """
    ).fetchone()

    passed = sum(1 for test in tests if test["status"] == "pass")
    return {
        "status": "pass" if passed == len(tests) else "fail",
        "invocation_id": invocation_id,
        "run_at": run_at.isoformat(),
        "dbt_version": dbt_version,
        "elapsed_seconds": round(float(elapsed), 4),
        "tests_passed": passed,
        "tests_total": len(tests),
        "tests": tests,
        "models": models,
        "source": {
            "table": "raw_github_events",
            "row_count": int(source_rows),
            "window_start": source_min.isoformat(),
            "window_end": source_max.isoformat(),
        },
    }
