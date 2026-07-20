"""Evaluate the contributor-churn classifier and export dashboard assets.

Performs a temporal 80/20 holdout rather than a random split: rows are ordered
by ``tenure_days`` descending so the longest-tenured (earliest-joined)
contributors form the training set and the newest cohort forms the test set.
This measures generalisation to contributors the model has never seen a
comparable history for, which is the deployment condition.

Reads through a zero-copy Arrow handoff from DuckDB and writes two PNGs into
``frontend/public/assets/`` for the Next.js dashboard to serve statically.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib
import numpy as np
import shap
import xgboost as xgb

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    ConfusionMatrixDisplay,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)

from ml.feature_extractor import (  # noqa: E402
    FEATURE_COLUMNS,
    FEATURE_LABELS,
    TARGET_COLUMN,
    enforce_schema,
)

_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _ROOT / "transform" / "argo.duckdb"
_MODEL_PATH = _ROOT / "ml" / "models" / "churn_xgb.json"
_ASSET_DIR = _ROOT / "frontend" / "public" / "assets"
_TRAINING_TABLE = "ml_contributor_churn_training"
_SPLIT_RATIO = 0.8

_BACKGROUND = "#020408"
_FOREGROUND = "#e2e8f0"


def load_arrow_frame():
    """Pull training rows out of DuckDB via a zero-copy Arrow table.

    Ordering matches ml/train_churn.py exactly so the holdout evaluated here
    is the same holdout the model was withheld from.
    """
    columns = ", ".join(["first_event_at", *FEATURE_COLUMNS, TARGET_COLUMN])
    connection = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        arrow_table = connection.execute(
            f"select {columns} from {_TRAINING_TABLE} order by first_event_at asc, actor_login asc"
        ).to_arrow_table()
    finally:
        connection.close()
    return arrow_table.to_pandas(zero_copy_only=False)


def temporal_split(frame):
    """Split the ordered frame into an older train head and a newer test tail."""
    cutoff = int(len(frame) * _SPLIT_RATIO)
    if cutoff == 0 or cutoff == len(frame):
        raise SystemExit("Training table is too small for an 80/20 temporal split.")
    train, test = frame.iloc[:cutoff], frame.iloc[cutoff:]
    print(f"Split boundary: {frame['first_event_at'].iloc[cutoff]}")
    return (
        enforce_schema(train),
        train[TARGET_COLUMN],
        enforce_schema(test),
        test[TARGET_COLUMN],
    )


def style_axes(axes) -> None:
    """Apply the dashboard's dark palette to a matplotlib axes object."""
    axes.set_facecolor(_BACKGROUND)
    axes.tick_params(colors=_FOREGROUND)
    axes.xaxis.label.set_color(_FOREGROUND)
    axes.yaxis.label.set_color(_FOREGROUND)
    axes.title.set_color(_FOREGROUND)
    for spine in axes.spines.values():
        spine.set_color("#1e293b")


def save_confusion_matrix(y_true, y_pred) -> Path:
    """Render and persist the holdout confusion matrix."""
    matrix = confusion_matrix(y_true, y_pred)
    figure, axes = plt.subplots(figsize=(5, 4.5), facecolor=_BACKGROUND)
    display = ConfusionMatrixDisplay(matrix, display_labels=["Retained", "Churned"])
    display.plot(ax=axes, cmap="cividis", colorbar=False, values_format="d")
    axes.set_title("Contributor Churn — Temporal Holdout")
    style_axes(axes)
    for text in axes.texts:
        text.set_color(_FOREGROUND)
    figure.tight_layout()
    path = _ASSET_DIR / "confusion_matrix.png"
    figure.savefig(path, dpi=160, facecolor=_BACKGROUND)
    plt.close(figure)
    return path


def save_shap_summary(model, x_test) -> Path:
    """Render and persist the global SHAP feature-importance summary."""
    labelled = x_test.rename(columns=FEATURE_LABELS)
    values = shap.TreeExplainer(model).shap_values(x_test)
    plt.figure(figsize=(7, 5.5), facecolor=_BACKGROUND)
    shap.summary_plot(values, labelled, show=False, color_bar=True)
    figure = plt.gcf()
    figure.set_facecolor(_BACKGROUND)
    for axes in figure.axes:
        style_axes(axes)
        for text in axes.get_yticklabels() + axes.get_xticklabels():
            text.set_color(_FOREGROUND)
    figure.tight_layout()
    path = _ASSET_DIR / "shap_summary.png"
    figure.savefig(path, dpi=160, facecolor=_BACKGROUND)
    plt.close(figure)
    return path


def main() -> None:
    """Score the persisted model on the newest cohort and export both plots."""
    if not _MODEL_PATH.exists():
        raise SystemExit(f"{_MODEL_PATH} not found; run ml/train_churn.py first.")

    frame = load_arrow_frame()
    if frame.empty:
        raise SystemExit(
            f"{_TRAINING_TABLE} is empty; run etl/land_github_data.py "
            "and 'dbt build' before evaluating."
        )

    x_train, _y_train, x_test, y_test = temporal_split(frame)

    model = xgb.XGBClassifier()
    model.load_model(str(_MODEL_PATH))

    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, 1]

    print(f"Train rows:  {len(x_train)}")
    print(f"Test rows:   {len(x_test)}")
    print(f"Positive rate (test): {float(np.mean(y_test)):.4f}")
    print(f"Precision:   {precision_score(y_test, predictions, zero_division=0):.4f}")
    print(f"Recall:      {recall_score(y_test, predictions, zero_division=0):.4f}")
    print(f"ROC-AUC:     {roc_auc_score(y_test, probabilities):.4f}")

    _ASSET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saved {save_confusion_matrix(y_test, predictions)}")
    print(f"Saved {save_shap_summary(model, x_test)}")


if __name__ == "__main__":
    main()
