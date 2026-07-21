"""Contributor risk endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Final

import duckdb
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends

from api.deps import get_db
from api.routers.predict import _cox_model, _median_survival, _survival_curve
from ml.feature_extractor import FEATURE_COLUMNS, enforce_schema

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

DbConn = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

_CANDIDATE_POOL: Final[int] = 200
_RESULT_LIMIT: Final[int] = 20


@router.get("/risk")
def contributors_at_risk(db: DbConn) -> list[dict[str, Any]]:
    """Return the fastest-decaying contributors among the highest-value ones.

    Scored live by the Cox survival model rather than read from a precomputed
    table, so the queue always reflects the currently deployed artifact.

    Ranking is two-stage on purpose: take the top contributors by event volume,
    then order that pool by predicted hazard. Ranking the whole cohort by hazard
    alone surfaces low-volume contributors whose departure costs nothing, which
    is not a retention queue anyone would action.

    A hazard ratio answers "who is decaying fastest", which is the ordering a
    triage queue needs; ``median_survival_days`` answers "how long do we have",
    which is what makes a row actionable. The classifier's probability answered
    neither without a threshold nobody agreed on.
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

    # One batch call over the whole candidate pool, not one call per row. The
    # curve is then assembled in Python against the startup-cached Breslow
    # baseline, so no row touches the booster twice.
    hazard_ratios: np.ndarray = np.asarray(
        _cox_model().predict(enforce_schema(frame)), dtype="float64"
    )
    frame = frame.assign(hazard_ratio=hazard_ratios).nlargest(_RESULT_LIMIT, "hazard_ratio")

    rows: list[dict[str, Any]] = []
    for row in frame.itertuples():
        hazard: float = float(row.hazard_ratio)
        curve: list[dict[str, float]] = _survival_curve(hazard)
        rows.append(
            {
                "contributor": str(row.actor_login),
                "primary_repo": str(row.primary_repo),
                "tenure_days": int(row.tenure_days),
                "total_events": int(row.total_events),
                "days_since_last_event": int(row.days_since_last_event),
                "hazard_ratio": round(hazard, 4),
                # None when survival never reaches 0.5 inside the 180-day
                # horizon. Coercing that to an int would invent a lapse date the
                # study never observed.
                "median_survival_days": _median_survival(curve),
                "survival_curve": curve,
            }
        )
    return rows
