"""Evaluate the Cox survival model and export dashboard assets.

The split is identical to ml/train_churn.py: rows ordered by ``first_event_at``
ascending and cut 80/20, so the holdout evaluated here is the same holdout the
model was withheld from.

Survival models are not scored with ROC-AUC, precision, or recall. Those
metrics require a hard label at a fixed horizon, which discards every
right-censored contributor -- exactly the population survival analysis exists
to handle. The concordance index replaces them: over all comparable pairs,
how often does the model rank the contributor who lapsed first as the riskier
of the two? 0.5 is a coin flip, 1.0 is perfect ordering.

Writes two PNGs into ``frontend/public/assets/`` for the Next.js dashboard:
Kaplan-Meier curves stratified by predicted risk, and a SHAP summary over the
log-hazard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb
import matplotlib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from sksurv.metrics import concordance_index_censored  # noqa: E402
from sksurv.nonparametric import kaplan_meier_estimator  # noqa: E402

from ml.feature_extractor import (  # noqa: E402
    FEATURE_COLUMNS,
    FEATURE_LABELS,
    TARGET_COLUMNS,
    enforce_schema,
)

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_DB_PATH: Final[Path] = _ROOT / "transform" / "argo.duckdb"
_MODEL_PATH: Final[Path] = _ROOT / "ml" / "models" / "churn_cox.json"
_ASSET_DIR: Final[Path] = _ROOT / "frontend" / "public" / "assets"
_TRAINING_TABLE: Final[str] = "ml_contributor_churn_training"
_SPLIT_COLUMN: Final[str] = "first_event_at"
_DURATION_COLUMN: Final[str] = TARGET_COLUMNS[0]
_EVENT_COLUMN: Final[str] = TARGET_COLUMNS[1]
_SPLIT_RATIO: Final[float] = 0.8

_BACKGROUND: Final[str] = "#050203"
_FOREGROUND: Final[str] = "#e2e8f0"
_STRATA: Final[list[tuple[str, str]]] = [
    ("Low risk (bottom tercile)", "#34d399"),
    ("Medium risk", "#f59e0b"),
    ("High risk (top tercile)", "#ef4444"),
]


def load_arrow_frame() -> pd.DataFrame:
    """Pull rows out of DuckDB via a zero-copy Arrow table.

    Ordering matches ml/train_churn.py exactly so the holdout evaluated here is
    the same holdout the model was withheld from.
    """
    columns: str = ", ".join([_SPLIT_COLUMN, *FEATURE_COLUMNS, _DURATION_COLUMN, _EVENT_COLUMN])
    connection = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        arrow_table = connection.execute(
            f"select {columns} from {_TRAINING_TABLE} order by {_SPLIT_COLUMN} asc, actor_login asc"
        ).to_arrow_table()
    finally:
        connection.close()
    return arrow_table.to_pandas(zero_copy_only=False)


def temporal_split(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Split the ordered frame into an earlier train head and a later holdout."""
    cutoff: int = int(len(frame) * _SPLIT_RATIO)
    if cutoff == 0 or cutoff == len(frame):
        raise SystemExit("Training table is too small for an 80/20 temporal split.")
    print(f"Split boundary: {frame[_SPLIT_COLUMN].iloc[cutoff]}")

    train: pd.DataFrame = frame.iloc[:cutoff]
    test: pd.DataFrame = frame.iloc[cutoff:]
    return (
        enforce_schema(train),
        enforce_schema(test),
        test[_DURATION_COLUMN],
        test[_EVENT_COLUMN],
    )


def concordance(duration: pd.Series, event: pd.Series, risk: np.ndarray) -> float:
    """Return Harrell's C-index for predicted hazard ratios."""
    result = concordance_index_censored(
        event.to_numpy(dtype=bool), duration.to_numpy(dtype="float64"), risk
    )
    return float(result[0])


def style_axes(axes: plt.Axes) -> None:
    """Apply the dashboard's dark palette to a matplotlib axes object."""
    axes.set_facecolor(_BACKGROUND)
    axes.tick_params(colors=_FOREGROUND)
    axes.xaxis.label.set_color(_FOREGROUND)
    axes.yaxis.label.set_color(_FOREGROUND)
    axes.title.set_color(_FOREGROUND)
    for spine in axes.spines.values():
        spine.set_color("#450a0a")


def save_km_curves(duration: pd.Series, event: pd.Series, risk: np.ndarray, c_index: float) -> Path:
    """Render Kaplan-Meier survival curves stratified by predicted risk.

    This is the survival equivalent of a confusion matrix: if the model ranks
    correctly, the high-risk curve falls fastest and the three bands never
    cross. Separation between them is the model's discrimination made visible.
    """
    terciles: np.ndarray = np.quantile(risk, [1 / 3, 2 / 3])
    band: np.ndarray = np.digitize(risk, terciles)

    figure, axes = plt.subplots(figsize=(7, 5), facecolor=_BACKGROUND)
    for index, (label, colour) in enumerate(_STRATA):
        mask: np.ndarray = band == index
        if mask.sum() == 0:
            continue
        times, survival = kaplan_meier_estimator(
            event.to_numpy(dtype=bool)[mask],
            duration.to_numpy(dtype="float64")[mask],
        )
        axes.step(
            times,
            survival,
            where="post",
            color=colour,
            linewidth=2,
            label=f"{label}  (n={int(mask.sum())})",
        )

    axes.set_xlabel("Days since first contribution")
    axes.set_ylabel("Probability still active")
    axes.set_title(f"Kaplan-Meier by predicted risk — C-index {c_index:.4f}")
    axes.set_ylim(0, 1.02)
    axes.grid(color="#1f2937", linestyle=":", linewidth=0.6)
    legend = axes.legend(facecolor=_BACKGROUND, edgecolor="#450a0a", fontsize=9)
    for text in legend.get_texts():
        text.set_color(_FOREGROUND)
    style_axes(axes)

    figure.tight_layout()
    path: Path = _ASSET_DIR / "survival_curves.png"
    figure.savefig(path, dpi=160, facecolor=_BACKGROUND)
    plt.close(figure)
    return path


def save_shap_summary(model: xgb.XGBRegressor, x_test: pd.DataFrame) -> Path:
    """Render the global SHAP summary over the predicted log-hazard."""
    labelled: pd.DataFrame = x_test.rename(columns=FEATURE_LABELS)
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
    path: Path = _ASSET_DIR / "shap_summary.png"
    figure.savefig(path, dpi=160, facecolor=_BACKGROUND)
    plt.close(figure)
    return path


def main() -> None:
    """Score the Cox model on the newest cohort and export both plots."""
    if not _MODEL_PATH.exists():
        raise SystemExit(f"{_MODEL_PATH} not found; run ml/train_churn.py first.")

    frame: pd.DataFrame = load_arrow_frame()
    if frame.empty:
        raise SystemExit(
            f"{_TRAINING_TABLE} is empty; run etl/land_github_data.py "
            "and 'dbt build' before evaluating."
        )

    x_train, x_test, d_test, e_test = temporal_split(frame)

    model = xgb.XGBRegressor()
    model.load_model(str(_MODEL_PATH))
    risk: np.ndarray = np.asarray(model.predict(x_test))
    c_index: float = concordance(d_test, e_test, risk)

    print(f"Train rows:        {len(x_train)}")
    print(f"Test rows:         {len(x_test)}")
    print(f"Events observed:   {int(e_test.sum())}")
    print(f"Right-censored:    {int((1 - e_test).sum())}")
    print(f"Median duration:   {float(d_test.median()):.0f} days")
    print(f"Holdout C-index:   {c_index:.4f}")
    print(f"Hazard range:      {risk.min():.3f} to {risk.max():.3f}")

    _ASSET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saved {save_km_curves(d_test, e_test, risk, c_index)}")
    print(f"Saved {save_shap_summary(model, x_test)}")


if __name__ == "__main__":
    main()
