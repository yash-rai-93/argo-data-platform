"""Contributor risk endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Final

import duckdb
import pandas as pd
from fastapi import APIRouter, Depends

from api.deps import get_db
from api.routers.predict import _model
from ml.feature_extractor import FEATURE_COLUMNS, enforce_schema

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

DbConn = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

_CANDIDATE_POOL: Final[int] = 200
_RESULT_LIMIT: Final[int] = 5


@router.get("/risk")
def contributors_at_risk(db: DbConn) -> list[dict[str, Any]]:
    """Return the highest-risk contributors among the highest-value ones.

    Scored live by the XGBoost model rather than read from a precomputed table,
    so the queue always reflects the currently deployed artifact.

    Ranking is two-stage on purpose: take the top contributors by event volume,
    then order that pool by predicted risk. Ranking the whole cohort by risk
    alone surfaces low-volume contributors whose departure costs nothing, which
    is not a retention queue anyone would action.
    """
    columns: str = ", ".join(["actor_login", "primary_repo", *FEATURE_COLUMNS])
    frame: pd.DataFrame = db.execute(
        f"""
        select {columns}
        from ml_contributor_churn_training
        order by total_events desc
        limit {_CANDIDATE_POOL}
        """
    ).df()

    if frame.empty:
        return []

    probabilities = _model().predict_proba(enforce_schema(frame))[:, 1]
    frame = frame.assign(risk_score=probabilities).nlargest(_RESULT_LIMIT, "risk_score")

    return [
        {
            "contributor": str(row.actor_login),
            "primary_repo": str(row.primary_repo),
            "tenure_days": int(row.tenure_days),
            "total_events": int(row.total_events),
            "days_since_last_event": int(row.days_since_last_event),
            "risk_score": round(float(row.risk_score), 4),
        }
        for row in frame.itertuples()
    ]
