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
