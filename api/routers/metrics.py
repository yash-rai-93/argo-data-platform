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
    """Return the latest MRR, ARR, and DAU."""
    return fetch_executive_metrics(db)


@router.get("/trend")
def mrr_trend(db: DbConn) -> list[dict]:
    """Return the last six complete months of MRR as a chronological trend."""
    rows = db.execute(
        """
        with monthly as (
            select
                date_trunc('month', f.event_timestamp) as m,
                sum(p.monthly_price) as mrr
            from fact_subscriptions as f
            inner join dim_subscription_plan as p
                on f.subscription_plan = p.subscription_plan
            where f.subscription_action = 'payment_completed'
                and f.event_timestamp < date_trunc('month', current_date)
            group by date_trunc('month', f.event_timestamp)
        )

        select strftime(m, '%b') as name, mrr
        from monthly
        order by m desc
        limit 6
        """
    ).fetchall()
    return [{"name": name, "mrr": int(mrr)} for name, mrr in reversed(rows)]


@router.get("/dau/sparkline")
def dau_sparkline(db: DbConn) -> list[int]:
    """Return the trailing seven days of active users as raw daily counts."""
    rows = db.execute(
        """
        select dau
        from metric_active_users
        where activity_date >= (
            select max(activity_date) - interval 7 day from metric_active_users
        )
        order by activity_date asc
        """
    ).fetchall()
    return [int(dau) for (dau,) in rows]


@router.get("/arr/sparkline")
def arr_sparkline(db: DbConn) -> list[int]:
    """Return the trailing six complete months of annualized recurring revenue."""
    rows = db.execute(
        """
        select arr
        from metric_mrr
        where revenue_month < date_trunc('month', current_date)
        order by revenue_month desc
        limit 6
        """
    ).fetchall()
    return [int(arr) for (arr,) in reversed(rows)]
