"""dbt Python model: batch churn scores for every user."""

from __future__ import annotations

import os
from pathlib import Path

import xgboost as xgb

_FEATURES = ["total_sessions", "avg_session_duration", "account_age_days"]


def model(dbt, session):
    """Score all users with the trained churn model and return the results."""
    dbt.config(materialized="table")

    users = dbt.ref("dim_users").df()
    sessions = dbt.ref("int_sessions").df()

    stats = (
        sessions.groupby("user_id")
        .agg(
            total_sessions=("session_id", "count"),
            avg_session_duration=("duration_seconds", "mean"),
        )
        .reset_index()
    )

    frame = users.merge(stats, on="user_id", how="left")
    frame["total_sessions"] = frame["total_sessions"].fillna(0)
    frame["avg_session_duration"] = frame["avg_session_duration"].fillna(0)

    as_of = frame["last_seen_at"].max()
    frame["account_age_days"] = (as_of - frame["first_seen_at"]).dt.days

    model_path = Path(os.getcwd()).resolve().parent / "ml" / "models" / "churn_xgb.json"
    classifier = xgb.XGBClassifier()
    classifier.load_model(str(model_path))

    features = frame[_FEATURES]
    frame["churn_probability"] = classifier.predict_proba(features)[:, 1]
    frame["predicted_churn_flag"] = classifier.predict(features).astype(int)

    return frame[
        [
            "user_id",
            "total_sessions",
            "account_age_days",
            "churn_probability",
            "predicted_churn_flag",
        ]
    ]
