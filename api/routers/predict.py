"""Contributor-churn prediction endpoint with SHAP attribution.

The Pydantic request schema is generated from ``FEATURE_COLUMNS`` in
``ml/feature_extractor.py`` so the API surface cannot drift from the trained
feature contract. Model and explainer are warmed at application startup by
``warm_cache`` so the first inference does not pay tree-traversal setup cost.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Final

import duckdb
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import get_db
from ml.feature_extractor import FEATURE_COLUMNS, FEATURE_LABELS, enforce_schema

router = APIRouter(prefix="/api/v1/predict", tags=["predict"])

DbConn = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_MODEL_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_xgb.json"
_PARAMS_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_xgb_params.json"
_COX_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_cox.json"
_TOP_N: Final[int] = 3

_CURVE_HORIZON: Final[int] = 180
"""Longest survival time the study can observe: 2023-07-01 to 2024-01-01."""

_CURVE_STEP: Final[int] = 5
_MILESTONES: Final[tuple[int, ...]] = (30, 60, 90)


@lru_cache
def _model() -> xgb.XGBClassifier:
    """Load and cache the trained churn classifier from the repo root."""
    model = xgb.XGBClassifier()
    model.load_model(str(_MODEL_PATH))
    return model


@lru_cache
def _cox_model() -> xgb.XGBRegressor:
    """Load and cache the Cox proportional-hazards survival model."""
    model = xgb.XGBRegressor()
    model.load_model(str(_COX_PATH))
    return model


@lru_cache
def _baseline_survival() -> tuple[tuple[int, ...], tuple[float, ...]]:
    """Estimate the baseline survival function via the Breslow estimator.

    ``survival:cox`` predicts a hazard ratio and nothing else. The proportional
    hazards form is::

        S(t | x) = S0(t) ** HR(x)

    so a per-contributor curve is impossible without S0, which XGBoost never
    stores. Breslow recovers it from the training risk sets::

        dH0(t) = d(t) / sum of HR over everyone still at risk at time t

    Computed on the training split only -- the holdout must stay unseen -- and
    cached for the process lifetime.
    """
    from ml.train_churn import load_training_frame, temporal_split

    x_train, _, d_train, e_train, _, _ = temporal_split(load_training_frame())
    hazard: np.ndarray = np.asarray(_cox_model().predict(x_train), dtype="float64")
    duration: np.ndarray = d_train.to_numpy(dtype="float64")
    event: np.ndarray = e_train.to_numpy(dtype="int64")

    event_times: np.ndarray = np.unique(duration[event == 1])
    cumulative: float = 0.0
    grid: list[int] = list(range(0, _CURVE_HORIZON + 1, _CURVE_STEP))
    baseline: list[float] = []
    cursor: int = 0

    for day in grid:
        while cursor < len(event_times) and event_times[cursor] <= day:
            time: float = event_times[cursor]
            at_risk: float = float(hazard[duration >= time].sum())
            deaths: int = int(((duration == time) & (event == 1)).sum())
            if at_risk > 0:
                cumulative += deaths / at_risk
            cursor += 1
        baseline.append(float(np.exp(-cumulative)))

    return tuple(grid), tuple(baseline)


def _survival_curve(hazard_ratio: float) -> list[dict[str, float]]:
    """Scale the baseline curve by one contributor's hazard ratio."""
    grid, baseline = _baseline_survival()
    return [
        {"day": day, "survival": round(float(value**hazard_ratio), 4)}
        for day, value in zip(grid, baseline, strict=True)
    ]


def _median_survival(curve: list[dict[str, float]]) -> int | None:
    """Return the first grid day where survival drops to or below 0.5."""
    for point in curve:
        if point["survival"] <= 0.5:
            return int(point["day"])
    return None


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
    # ml.train_churn is now the Cox survival trainer and returns a different
    # tuple shape. The binary classifier's split lives in ml.train_classifier,
    # which still owns the artifact this endpoint serves.
    from ml.train_classifier import load_training_frame, temporal_split

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
    # Breslow reads the whole training split and is O(events x rows). Paying it
    # once at startup keeps it off the request path entirely.
    _cox_model().predict(frame)
    _baseline_survival()


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

    Two models answer two different questions from one payload. The classifier
    returns ``probability`` -- will this contributor lapse by the horizon -- and
    the Cox model returns ``hazard_ratio`` and a full survival curve, which say
    how fast they are decaying and how long is left.

    ``log_odds`` is the raw additive margin the classifier actually optimises:
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

    hazard_ratio: float = float(_cox_model().predict(frame)[0])
    curve: list[dict[str, float]] = _survival_curve(hazard_ratio)
    milestones: list[dict[str, float]] = [
        point for point in curve if int(point["day"]) in _MILESTONES
    ]

    return {
        "churn_prediction": prediction,
        "probability": probability,
        "log_odds": log_odds,
        "base_log_odds": base_value,
        "shap_attribution": attribution,
        "top_factors": top_factors,
        "hazard_ratio": round(hazard_ratio, 4),
        "median_survival_days": _median_survival(curve),
        "survival_curve": curve,
        "survival_milestones": milestones,
    }


@router.get("/model-card")
def model_card(db: DbConn) -> dict[str, Any]:
    """Return the deployed model's full specification.

    Everything is read from the artifacts on disk and the warehouse, never
    hardcoded, so the settings page cannot describe a model that is not the
    one actually serving predictions.
    """
    params: dict[str, Any] = {}
    if _PARAMS_PATH.exists():
        params = json.loads(_PARAMS_PATH.read_text(encoding="utf-8"))

    booster = _model().get_booster()
    stat = _MODEL_PATH.stat() if _MODEL_PATH.exists() else None

    window_start, window_end, source_rows = db.execute(
        "select min(created_at), max(created_at), count(*) from raw_github_events"
    ).fetchone()
    cohort_rows, churn_rate = db.execute(
        "select count(*), avg(is_churned) from ml_contributor_churn_training"
    ).fetchone()
    repo_count = db.execute("select count(distinct repo_name) from raw_github_events").fetchone()[0]

    return {
        "algorithm": "XGBoost gradient-boosted trees (XGBClassifier)",
        "objective": "binary:logistic",
        "artifact": _MODEL_PATH.name,
        "artifact_bytes": stat.st_size if stat else 0,
        "artifact_modified": (
            datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat() if stat else None
        ),
        "n_trees": int(len(booster.get_dump())),
        "n_features": len(FEATURE_COLUMNS),
        "features": [
            {"name": name, "label": FEATURE_LABELS.get(name, name)} for name in FEATURE_COLUMNS
        ],
        "target": "is_churned",
        "hyperparameters": params.get("best_params", {}),
        "scale_pos_weight": params.get("scale_pos_weight"),
        "cv_splits": params.get("cv_splits"),
        "cv_roc_auc": params.get("best_cv_roc_auc"),
        "decision_threshold": 0.5,
        "explainer": "SHAP TreeExplainer (log-odds margin contributions)",
        "data": {
            "source": "githubarchive.day.* via BigQuery",
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "source_rows": int(source_rows),
            "repos": int(repo_count),
            "cohort_rows": int(cohort_rows),
            "cohort_churn_rate": round(float(churn_rate), 4),
            "eligibility": ">=5 events across >=3 distinct active days",
            "observation_window": "2023-07-01 to 2023-11-01 (half-open)",
            "target_window": "2023-11-01 to 2024-01-01 (half-open)",
        },
    }


@router.get("/registry")
def model_registry(db: DbConn) -> list[dict[str, Any]]:
    """Return every recorded training iteration in chronological order.

    Rows are appended by ml/train_churn.py on each run, so the history grows
    from execution. ``comparable`` is false for the synthetic baseline, which
    scored a different target on data that no longer exists.
    """
    rows = db.execute(
        """
        select version, recorded_at, dataset, split_strategy, n_features,
               n_rows, n_train, n_test, churn_rate_test, cv_roc_auc,
               holdout_roc_auc, precision_score, recall_score, best_params,
               change_summary, comparable
        from meta_model_registry
        order by recorded_at asc
        """
    ).fetchall()

    return [
        {
            "version": version,
            "recorded_at": recorded_at.isoformat(),
            "dataset": dataset,
            "split_strategy": split,
            "n_features": int(n_features),
            "n_rows": int(n_rows),
            "n_train": int(n_train),
            "n_test": int(n_test),
            "churn_rate_test": None if churn is None else round(float(churn), 4),
            "cv_roc_auc": None if cv is None else round(float(cv), 4),
            "holdout_roc_auc": None if auc is None else round(float(auc), 4),
            "precision": None if prec is None else round(float(prec), 4),
            "recall": None if rec is None else round(float(rec), 4),
            "best_params": params,
            "change_summary": summary,
            "comparable": bool(comparable),
        }
        for (
            version,
            recorded_at,
            dataset,
            split,
            n_features,
            n_rows,
            n_train,
            n_test,
            churn,
            cv,
            auc,
            prec,
            rec,
            params,
            summary,
            comparable,
        ) in rows
    ]


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
