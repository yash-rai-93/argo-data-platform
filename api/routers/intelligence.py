"""Decision-intelligence endpoints."""

from __future__ import annotations

from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends

from api.deps import fetch_executive_metrics, get_db
from ml.llm_engine import InsightEngine

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])

DbConn = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]


@router.get("/summary")
def executive_summary(db: DbConn) -> dict:
    """Return a strategic narrative and its reasoning trace for the latest metrics."""
    metrics = fetch_executive_metrics(db)
    engine = InsightEngine()
    return engine.generate_executive_summary(metrics)
