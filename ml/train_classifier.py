"""Train, tune, and persist an XGBoost contributor-churn classifier.

Reads the leakage-free training set produced by the dbt model
``main.ml_contributor_churn_training`` directly from the DuckDB warehouse.

Two independent leakage controls are enforced:

1. The outer split is strictly chronological. Rows arrive ordered by
   ``first_event_at`` ascending and are cut 80/20, so the model is fitted on
   contributors who joined earlier and scored on the newest cohort only. A
   stratified random split would let contemporaneous cohorts sit on both sides
   of the cut and inflate every reported metric.
2. Cross-validation uses ``TimeSeriesSplit``, giving expanding-window forward
   chaining over that already-ordered training head. Every validation fold is
   strictly later than the training folds that produced it.

Class imbalance is handled by ``scale_pos_weight`` alone. Synthetic
oversampling was removed deliberately: SMOTE interpolates between contributor
behaviour vectors to invent contributors that cannot exist, and stacking it on
top of gradient reweighting double-corrects the imbalance, driving recall to
near 1.0 while precision collapses.

``first_event_at`` is read for ordering alone. ``enforce_schema`` projects the
matrix onto ``FEATURE_COLUMNS``, which excludes it, so no raw timestamp can
become a feature.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import duckdb
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline

from ml.feature_extractor import FEATURE_COLUMNS, TARGET_COLUMN, enforce_schema
from ml.model_registry import record_run

_VERSION: Final[str] = "v2.2-boundary-probe"  # classifier lineage
_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_DB_PATH: Final[Path] = _ROOT / "transform" / "argo.duckdb"
_MODEL_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_xgb.json"
_PARAMS_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_xgb_params.json"
_TRAINING_TABLE: Final[str] = "main.ml_contributor_churn_training"
_SPLIT_COLUMN: Final[str] = "first_event_at"
_SPLIT_RATIO: Final[float] = 0.8
_CV_SPLITS: Final[int] = 3
_RANDOM_STATE: Final[int] = 42

_PARAM_GRID: Final[dict[str, list[float | int]]] = {
    "xgb__max_depth": [1, 2],
    "xgb__n_estimators": [100, 200, 400],
    "xgb__min_child_weight": [5, 10],
    "xgb__learning_rate": [0.01, 0.05],
    "xgb__subsample": [0.5, 0.6],
}
"""Boundary-probe grid. The prior search selected max_depth=2 and
n_estimators=100 -- both grid edges -- so the optimum may lie outside what was
offered. This extends depth downward to decision stumps and the ensemble upward
to 400 rounds, trading per-tree capacity for ensemble depth, which is the
correct bias/variance direction on 2,426 rows. 2*3*2*2*2 = 48 candidates over
3 folds = 144 fits."""


def load_training_frame() -> pd.DataFrame:
    """Pull contributor training rows out of DuckDB in chronological order.

    Ordering is applied in SQL so the temporal cut never depends on pandas
    sort stability. ``actor_login`` is the tiebreaker, making the split
    deterministic when many contributors share a first-event timestamp.
    """
    columns: str = ", ".join([_SPLIT_COLUMN, *FEATURE_COLUMNS, TARGET_COLUMN])
    connection = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        return connection.execute(
            f"select {columns} from {_TRAINING_TABLE} order by {_SPLIT_COLUMN} asc, actor_login asc"
        ).fetch_df()
    finally:
        connection.close()


def temporal_split(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Cut the ordered frame into an earlier train head and a later holdout."""
    cutoff: int = int(len(frame) * _SPLIT_RATIO)
    if cutoff == 0 or cutoff == len(frame):
        raise SystemExit("Training table is too small for an 80/20 temporal split.")

    train: pd.DataFrame = frame.iloc[:cutoff]
    test: pd.DataFrame = frame.iloc[cutoff:]
    return (
        enforce_schema(train),
        train[TARGET_COLUMN],
        enforce_schema(test),
        test[TARGET_COLUMN],
    )


def imbalance_weight(target: pd.Series) -> float:
    """Return ``scale_pos_weight`` for the training labels only.

    Defined as retained over churned. XGBoost multiplies the positive class
    gradient by this factor, so the ratio must be negatives/positives for the
    two classes to contribute equal gradient mass. Inverting it to
    churned/retained would scale the already-rare positive class *down* and
    make the imbalance worse.
    """
    positives: int = int(target.sum())
    negatives: int = int(len(target) - positives)
    if positives == 0:
        raise SystemExit("Training split contains no churned contributors.")
    return negatives / positives


def build_pipeline(scale_pos_weight: float) -> Pipeline:
    """Wrap the classifier in a single-step pipeline.

    The pipeline is retained even with one step so the ``xgb__`` parameter grid
    prefixes stay stable and a scaler or selector can be inserted later without
    touching the search configuration.
    """
    return Pipeline(
        steps=[
            (
                "xgb",
                xgb.XGBClassifier(
                    eval_metric="logloss",
                    scale_pos_weight=scale_pos_weight,
                    random_state=_RANDOM_STATE,
                    n_jobs=-1,
                    tree_method="hist",
                ),
            ),
        ]
    )


def main() -> None:
    """Load, split chronologically, grid-search, and export the best model."""
    frame: pd.DataFrame = load_training_frame()
    if frame.empty:
        raise SystemExit(
            f"{_TRAINING_TABLE} is empty; run etl/land_github_data.py "
            "and 'dbt build' before training."
        )

    x_train, y_train, x_test, y_test = temporal_split(frame)

    scale_pos_weight: float = imbalance_weight(y_train)

    print(f"Rows:             {len(frame)}")
    print(f"Split boundary:   {frame[_SPLIT_COLUMN].iloc[len(x_train)]}")
    print(f"Train / test:     {len(x_train)} / {len(x_test)}")
    print(f"Churn rate train: {y_train.mean():.4f}")
    print(f"Churn rate test:  {y_test.mean():.4f}")
    print(f"scale_pos_weight: {scale_pos_weight:.4f}")

    search = GridSearchCV(
        estimator=build_pipeline(scale_pos_weight),
        param_grid=_PARAM_GRID,
        scoring="roc_auc",
        cv=TimeSeriesSplit(n_splits=_CV_SPLITS),
        n_jobs=-1,
        refit=True,
        verbose=1,
    )
    search.fit(x_train, y_train)

    print(f"Best CV ROC-AUC:  {search.best_score_:.4f}")
    print(f"Best params:      {search.best_params_}")

    model: xgb.XGBClassifier = search.best_estimator_.named_steps["xgb"]
    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, 1]
    holdout_precision = float(precision_score(y_test, predictions, zero_division=0))
    holdout_recall = float(recall_score(y_test, predictions, zero_division=0))
    holdout_auc = float(roc_auc_score(y_test, probabilities))
    print(f"Holdout accuracy:  {accuracy_score(y_test, predictions):.4f}")
    print(f"Holdout precision: {holdout_precision:.4f}")
    print(f"Holdout recall:    {holdout_recall:.4f}")
    print(f"Holdout ROC-AUC:   {holdout_auc:.4f}")

    record_run(
        {
            "version": _VERSION,
            "recorded_at": datetime.now(UTC),
            "dataset": f"GitHub Archive, {_TRAINING_TABLE}",
            "split_strategy": (
                f"chronological {_SPLIT_RATIO:.0%}/"
                f"{1 - _SPLIT_RATIO:.0%} + TimeSeriesSplit({_CV_SPLITS})"
            ),
            "n_features": len(FEATURE_COLUMNS),
            "n_rows": len(frame),
            "n_train": len(x_train),
            "n_test": len(x_test),
            "churn_rate_test": float(y_test.mean()),
            "cv_roc_auc": float(search.best_score_),
            "holdout_roc_auc": holdout_auc,
            "precision_score": holdout_precision,
            "recall_score": holdout_recall,
            "best_params": ", ".join(
                f"{key.removeprefix('xgb__')}={value}"
                for key, value in sorted(search.best_params_.items())
            ),
            "change_summary": "Automatically recorded by ml/train_churn.py.",
            "comparable": True,
        }
    )
    print(f"Recorded run as {_VERSION} in the model registry")

    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(_MODEL_PATH)
    _PARAMS_PATH.write_text(
        json.dumps(
            {
                "best_params": search.best_params_,
                "best_cv_roc_auc": search.best_score_,
                "scale_pos_weight": scale_pos_weight,
                "cv_splits": _CV_SPLITS,
                "features": FEATURE_COLUMNS,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved model to {_MODEL_PATH}")
    print(f"Saved params to {_PARAMS_PATH}")


if __name__ == "__main__":
    main()
