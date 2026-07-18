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
    """Return the latest MRR, ARR, and DAU from the semantic layer."""
    mrr, arr = db.execute(
        "select mrr, arr from metric_mrr order by revenue_month desc limit 1"
    ).fetchone()
    (dau,) = db.execute(
        "select dau from metric_active_users order by activity_date desc limit 1"
    ).fetchone()
    return {"mrr": mrr, "arr": arr, "dau": dau}
