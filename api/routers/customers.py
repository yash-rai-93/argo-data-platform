"""Customer risk endpoints."""

from __future__ import annotations

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends

from api.deps import get_db

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

DbConn = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]


@router.get("/risk")
def customers_at_risk(db: DbConn) -> list[dict]:
    """Return the highest churn-risk users with their key features."""
    columns = ["user_id", "account_age_days", "total_sessions", "churn_probability"]
    rows = db.execute(
        """
        select user_id, account_age_days, total_sessions, churn_probability
        from ml_churn_scores
        where churn_probability > 0.5
        order by churn_probability desc
        limit 5
        """
    ).fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]
