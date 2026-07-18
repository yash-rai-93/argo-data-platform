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
    """Return MRR, ARR, and DAU, smoothed past the edge of the generated window.

    MRR and ARR use the second-to-last complete month; DAU is a 7-day trailing
    average, both avoiding the partial final period.
    """
    mrr, arr = db.execute(
        """
        select mrr, arr
        from metric_mrr
        where revenue_month = (
            select max(revenue_month) from metric_mrr
            where revenue_month < (select max(revenue_month) from metric_mrr)
        )
        """
    ).fetchone()
    (dau,) = db.execute(
        """
        select cast(avg(dau) as int)
        from metric_active_users
        where activity_date >= (
            select max(activity_date) - interval 7 day from metric_active_users
        )
        """
    ).fetchone()
    return {"mrr": mrr, "arr": arr, "dau": dau}
