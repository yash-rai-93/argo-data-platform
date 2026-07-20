"""Contributor-churn prediction endpoint with SHAP attribution.

The Pydantic request schema is generated from ``FEATURE_COLUMNS`` in
``ml/feature_extractor.py`` so the API surface cannot drift from the trained
feature contract. Model and explainer are warmed at application startup by
``warm_cache`` so the first inference does not pay tree-traversal setup cost.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ml.feature_extractor import FEATURE_COLUMNS, FEATURE_LABELS, enforce_schema

router = APIRouter(prefix="/api/v1/predict", tags=["predict"])

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_MODEL_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_xgb.json"
_TOP_N: Final[int] = 3


@lru_cache
def _model() -> xgb.XGBClassifier:
    """Load and cache the trained churn classifier from the repo root."""
    model = xgb.XGBClassifier()
    model.load_model(str(_MODEL_PATH))
    return model


@lru_cache
def _explainer() -> shap.TreeExplainer:
    """Load and cache a SHAP tree explainer over the churn model."""
    return shap.TreeExplainer(_model())


@lru_cache
def _holdout_scores() -> tuple[tuple[int, ...], tuple[float, ...]]:
    """Score the temporal holdout once and cache the result for the session.

    Reuses ``load_training_frame`` and ``temporal_split`` from the training
    module rather than reimplementing the cut, so the rows served here are
    provably the same 20% the model was never fitted on. Reimplementing the
    split would risk silently scoring training rows and reporting a confusion
    matrix that flatters the model.
    """
    from ml.train_churn import load_training_frame, temporal_split

    _, _, x_test, y_test = temporal_split(load_training_frame())
    probabilities = _model().predict_proba(x_test)[:, 1]
    return (
        tuple(int(label) for label in y_test),
        tuple(round(float(prob), 4) for prob in probabilities),
    )


def warm_cache() -> None:
    """Build the model and explainer caches, then force one dry inference.

    Called from the FastAPI lifespan handler. The dry run materialises the
    explainer's internal tree structures so request latency is steady-state
    from the very first call.
    """
    frame: pd.DataFrame = enforce_schema(pd.DataFrame([dict.fromkeys(FEATURE_COLUMNS, 0.0)]))
    _model().predict_proba(frame)
    _explainer().shap_values(frame)


class ChurnPredictionRequest(BaseModel):
    """Observation-window behaviour for a single GitHub contributor.

    Every field is measured strictly before the observation cutoff, mirroring
    the dbt training model, so no target-window signal can enter inference.

    Field names and count must stay identical to ``FEATURE_COLUMNS``; the
    module-level assertion below fails at import time if they diverge.
    """

    total_events: int = Field(ge=0)
    distinct_repos: int = Field(ge=0)
    active_days: int = Field(ge=0)
    commit_events: int = Field(ge=0)
    pull_request_events: int = Field(ge=0)
    issue_events: int = Field(ge=0)
    comment_events: int = Field(ge=0)
    engagement_events: int = Field(ge=0)
    release_events: int = Field(ge=0)
    weekend_ratio: float = Field(ge=0.0, le=1.0)
    events_per_active_day: float = Field(ge=0.0)
    tenure_days: int = Field(ge=0)
    days_since_last_event: int = Field(ge=0)
    """Trajectory features. Share of observed activity landing in the final 30
    days, and the raw plus normalised event delta between the two halves of the
    observation window. Deceleration is signed: positive means slowing down."""
    velocity_30d: float = Field(ge=0.0, le=1.0)
    deceleration_score: float
    deceleration_ratio: float = Field(ge=-1.0, le=1.0)


if list(ChurnPredictionRequest.model_fields) != FEATURE_COLUMNS:
    raise RuntimeError(
        "ChurnPredictionRequest has drifted from FEATURE_COLUMNS: "
        f"{list(ChurnPredictionRequest.model_fields)} != {FEATURE_COLUMNS}"
    )


@router.post("/churn")
def predict_churn(features: ChurnPredictionRequest) -> dict[str, Any]:
    """Score a contributor for churn risk and explain the prediction.

    ``log_odds`` is the raw additive margin the model actually optimises:
    the explainer base value plus every SHAP contribution. ``shap_attribution``
    carries all 16 contributions for the dashboard chart, while ``top_factors``
    isolates the three largest by absolute impact.
    """
    frame: pd.DataFrame = enforce_schema(pd.DataFrame([features.model_dump()]))

    model: xgb.XGBClassifier = _model()
    prediction: int = int(model.predict(frame)[0])
    probability: float = float(model.predict_proba(frame)[0][1])

    explainer: shap.TreeExplainer = _explainer()
    values: np.ndarray = np.asarray(explainer.shap_values(frame))[0]
    base_value: float = float(np.ravel(explainer.expected_value)[0])
    log_odds: float = base_value + float(values.sum())

    attribution: list[dict[str, Any]] = [
        {
            "feature": FEATURE_LABELS.get(name, name),
            "contribution": round(float(value), 4),
        }
        for name, value in zip(FEATURE_COLUMNS, values, strict=True)
    ]
    attribution.sort(key=lambda item: item["contribution"], reverse=True)

    top_factors: list[dict[str, Any]] = sorted(
        attribution, key=lambda item: abs(item["contribution"]), reverse=True
    )[:_TOP_N]

    return {
        "churn_prediction": prediction,
        "probability": probability,
        "log_odds": log_odds,
        "base_log_odds": base_value,
        "shap_attribution": attribution,
        "top_factors": top_factors,
    }


@router.get("/simulate/threshold")
def simulate_threshold() -> dict[str, Any]:
    """Return the scored temporal holdout for client-side threshold sweeping.

    Ships raw ``(y_true, y_prob)`` pairs rather than a precomputed matrix so
    the frontend can recompute TP/FP/TN/FN at any threshold with zero further
    round trips. At ~600 rows the payload is a few kilobytes.
    """
    labels, probabilities = _holdout_scores()
    return {
        "n": len(labels),
        "positive_rate": round(sum(labels) / len(labels), 4) if labels else 0.0,
        "y_true": list(labels),
        "y_prob": list(probabilities),
    }
