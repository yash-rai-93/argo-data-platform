"""Churn prediction endpoint."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
import shap
import xgboost as xgb
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/predict", tags=["predict"])

_MODEL_PATH = Path(__file__).resolve().parents[2] / "ml" / "models" / "churn_xgb.json"
_FEATURES = ["total_sessions", "avg_session_duration", "account_age_days"]
_LABELS = {
    "total_sessions": "Total Sessions",
    "avg_session_duration": "Avg Session Duration",
    "account_age_days": "Account Age",
}


@lru_cache
def _model() -> xgb.XGBClassifier:
    """Load and cache the trained churn classifier."""
    model = xgb.XGBClassifier()
    model.load_model(str(_MODEL_PATH))
    return model


@lru_cache
def _explainer() -> shap.TreeExplainer:
    """Load and cache a SHAP tree explainer over the churn model."""
    return shap.TreeExplainer(_model())


class ChurnFeatures(BaseModel):
    total_sessions: int
    avg_session_duration: float
    account_age_days: int


@router.post("/churn")
def predict_churn(features: ChurnFeatures) -> dict:
    """Score a single user for churn risk."""
    frame = pd.DataFrame([features.model_dump()], columns=_FEATURES)
    model = _model()
    prediction = int(model.predict(frame)[0])
    probability = float(model.predict_proba(frame)[0][1])

    values = _explainer().shap_values(frame)[0]
    attribution = sorted(
        (
            {"feature": _LABELS[name], "impact": round(float(value), 3)}
            for name, value in zip(_FEATURES, values, strict=True)
        ),
        key=lambda item: item["impact"],
        reverse=True,
    )
    return {
        "churn_prediction": prediction,
        "probability": probability,
        "shap_attribution": attribution,
    }
