"""Train and persist an XGBoost Cox survival model for contributor churn.

Binary classification answers "will this contributor lapse?". Survival analysis
answers the more useful question: "how long do we have, and who is decaying
fastest?" -- and it does so without throwing away the contributors who had not
lapsed yet when the study window closed.

Those right-censored contributors are the reason this matters. A classifier
must label them "retained", which is only true up to the cutoff; it cannot
represent "still active at day 184, outcome unknown". Cox handles them
natively by contributing them to the risk set until censoring and no further.

Label encoding for ``survival:cox`` in XGBoost:

    y = +duration   observed event (contributor lapsed)
    y = -duration   right-censored (still active at the study cutoff)

The model predicts a hazard ratio, not a probability. Higher means decaying
faster. There is no threshold and no confusion matrix -- ranking quality is
measured by the concordance index.

Leakage controls are unchanged from the classifier: the outer split is strictly
chronological on ``first_event_at``, cross-validation uses expanding-window
forward chaining, and the split key is never a feature.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import duckdb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sksurv.metrics import concordance_index_censored

from ml.feature_extractor import FEATURE_COLUMNS, TARGET_COLUMNS, enforce_schema
from ml.model_registry import record_run

_VERSION: Final[str] = "v3.0-survival-cox"
_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_DB_PATH: Final[Path] = _ROOT / "transform" / "argo.duckdb"
_MODEL_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_cox.json"
_PARAMS_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_cox_params.json"
_TRAINING_TABLE: Final[str] = "main.ml_contributor_churn_training"
_SPLIT_COLUMN: Final[str] = "first_event_at"
_DURATION_COLUMN: Final[str] = TARGET_COLUMNS[0]
_EVENT_COLUMN: Final[str] = TARGET_COLUMNS[1]
_SPLIT_RATIO: Final[float] = 0.8
_CV_SPLITS: Final[int] = 3
_RANDOM_STATE: Final[int] = 42

_PARAM_GRID: Final[dict[str, list[float | int]]] = {
    "max_depth": [2, 3],
    "n_estimators": [100, 200, 400],
    "min_child_weight": [5, 10],
    "learning_rate": [0.01, 0.05],
    "subsample": [0.6, 0.8],
}
"""Same regularisation-first shape the classifier converged on. Cox partial
likelihood is prone to overfitting on 2.4k rows, so depth stays shallow."""


def load_training_frame() -> pd.DataFrame:
    """Pull contributor rows out of DuckDB in chronological order."""
    columns: str = ", ".join([_SPLIT_COLUMN, *FEATURE_COLUMNS, _DURATION_COLUMN, _EVENT_COLUMN])
    connection = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        return connection.execute(
            f"select {columns} from {_TRAINING_TABLE} order by {_SPLIT_COLUMN} asc, actor_login asc"
        ).fetch_df()
    finally:
        connection.close()


def cox_label(duration: pd.Series, event: pd.Series) -> np.ndarray:
    """Encode duration and event into XGBoost's signed Cox label.

    Positive values are observed events, negative values are right-censored
    observations. Zero-length durations are clamped to 1 day because a signed
    encoding cannot represent a censored zero.
    """
    days: np.ndarray = np.maximum(duration.to_numpy(dtype="float64"), 1.0)
    observed: np.ndarray = event.to_numpy(dtype="int64") == 1
    return np.where(observed, days, -days)


def survival_array(duration: pd.Series, event: pd.Series) -> np.ndarray:
    """Build the structured array scikit-survival's metrics expect."""
    return np.array(
        list(
            zip(
                event.to_numpy(dtype=bool),
                duration.to_numpy(dtype="float64"),
                strict=True,
            )
        ),
        dtype=[("event", "?"), ("duration", "<f8")],
    )


def temporal_split(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Cut the ordered frame into an earlier train head and a later holdout.

    Returns the schema-enforced feature matrices plus the duration and event
    vectors for each side. ``enforce_schema`` drops ``first_event_at``, so the
    split key never reaches the model.
    """
    cutoff: int = int(len(frame) * _SPLIT_RATIO)
    if cutoff == 0 or cutoff == len(frame):
        raise SystemExit("Training table is too small for an 80/20 temporal split.")

    train: pd.DataFrame = frame.iloc[:cutoff]
    test: pd.DataFrame = frame.iloc[cutoff:]
    return (
        enforce_schema(train),
        enforce_schema(test),
        train[_DURATION_COLUMN],
        train[_EVENT_COLUMN],
        test[_DURATION_COLUMN],
        test[_EVENT_COLUMN],
    )


def concordance(duration: pd.Series, event: pd.Series, risk: np.ndarray) -> float:
    """Return Harrell's C-index for predicted hazard ratios.

    0.5 is random ranking, 1.0 is perfect. Unlike ROC-AUC this is defined over
    censored data: only comparable pairs, where the earlier subject is known to
    have failed first, contribute to the score.
    """
    result = concordance_index_censored(
        event.to_numpy(dtype=bool), duration.to_numpy(dtype="float64"), risk
    )
    return float(result[0])


def build_estimator() -> xgb.XGBRegressor:
    """Assemble the Cox proportional-hazards booster.

    ``scale_pos_weight`` is deliberately absent: Cox partial likelihood already
    accounts for censoring through the risk set, so reweighting classes would
    distort the hazard rather than balance it.
    """
    return xgb.XGBRegressor(
        objective="survival:cox",
        eval_metric="cox-nloglik",
        random_state=_RANDOM_STATE,
        n_jobs=-1,
        tree_method="hist",
    )


def cox_scorer(estimator: xgb.XGBRegressor, x: pd.DataFrame, y: np.ndarray) -> float:
    """Score a fold by C-index, decoding the signed Cox label back to (t, e)."""
    duration: pd.Series = pd.Series(np.abs(y))
    event: pd.Series = pd.Series((y > 0).astype(int))
    return concordance(duration, event, np.asarray(estimator.predict(x)))


def main() -> None:
    """Load, split chronologically, grid-search, and export the Cox model."""
    frame: pd.DataFrame = load_training_frame()
    if frame.empty:
        raise SystemExit(
            f"{_TRAINING_TABLE} is empty; run etl/land_github_data.py "
            "and 'dbt build' before training."
        )

    x_train, x_test, d_train, e_train, d_test, e_test = temporal_split(frame)
    y_train: np.ndarray = cox_label(d_train, e_train)

    print(f"Rows:              {len(frame)}")
    print(f"Split boundary:    {frame[_SPLIT_COLUMN].iloc[len(x_train)]}")
    print(f"Train / test:      {len(x_train)} / {len(x_test)}")
    print(f"Events (train):    {int(e_train.sum())} of {len(e_train)}")
    print(f"Censored (train):  {int((1 - e_train).sum())}")
    print(f"Events (test):     {int(e_test.sum())} of {len(e_test)}")
    print(f"Median duration:   {float(d_train.median()):.0f} days")

    search = GridSearchCV(
        estimator=build_estimator(),
        param_grid=_PARAM_GRID,
        scoring=cox_scorer,
        cv=TimeSeriesSplit(n_splits=_CV_SPLITS),
        n_jobs=-1,
        refit=True,
        verbose=1,
    )
    search.fit(x_train, y_train)

    model: xgb.XGBRegressor = search.best_estimator_
    train_risk: np.ndarray = np.asarray(model.predict(x_train))
    test_risk: np.ndarray = np.asarray(model.predict(x_test))
    cv_cindex: float = float(search.best_score_)
    train_cindex: float = concordance(d_train, e_train, train_risk)
    holdout_cindex: float = concordance(d_test, e_test, test_risk)

    print(f"Best CV C-index:   {cv_cindex:.4f}")
    print(f"Best params:       {search.best_params_}")
    print(f"Train C-index:     {train_cindex:.4f}")
    print(f"Holdout C-index:   {holdout_cindex:.4f}")
    print(f"Hazard range:      {test_risk.min():.3f} to {test_risk.max():.3f}")

    record_run(
        {
            "version": _VERSION,
            "recorded_at": datetime.now(UTC),
            "dataset": f"GitHub Archive, {_TRAINING_TABLE} (survival targets)",
            "split_strategy": (
                f"chronological {_SPLIT_RATIO:.0%}/"
                f"{1 - _SPLIT_RATIO:.0%} + TimeSeriesSplit({_CV_SPLITS})"
            ),
            "n_features": len(FEATURE_COLUMNS),
            "n_rows": len(frame),
            "n_train": len(x_train),
            "n_test": len(x_test),
            "churn_rate_test": float(e_test.mean()),
            "cv_roc_auc": cv_cindex,
            "holdout_roc_auc": holdout_cindex,
            "precision_score": None,
            "recall_score": None,
            "best_params": ", ".join(
                f"{key}={value}" for key, value in sorted(search.best_params_.items())
            ),
            "change_summary": (
                "Cox proportional hazards. Metrics are C-index, not ROC-AUC: "
                "the model ranks time-to-lapse and keeps right-censored "
                "contributors in the risk set instead of mislabelling them."
            ),
            "comparable": False,
        }
    )

    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(_MODEL_PATH)
    payload: dict[str, Any] = {
        "objective": "survival:cox",
        "eval_metric": "cox-nloglik",
        "best_params": search.best_params_,
        "cv_c_index": cv_cindex,
        "train_c_index": train_cindex,
        "holdout_c_index": holdout_cindex,
        "cv_splits": _CV_SPLITS,
        "features": FEATURE_COLUMNS,
        "targets": TARGET_COLUMNS,
    }
    _PARAMS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved model to {_MODEL_PATH}")
    print(f"Saved params to {_PARAMS_PATH}")


if __name__ == "__main__":
    main()
