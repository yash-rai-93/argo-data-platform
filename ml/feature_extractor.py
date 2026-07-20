"""Contributor-churn feature schema and warehouse extraction.

Defines the canonical feature contract shared by training, evaluation, and
serving so the three can never drift apart. Rows are read from the dbt model
``ml_contributor_churn_training``, which already applies the leakage-free
observation/target window split, so no windowing is repeated here.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Final

import duckdb
import pandas as pd

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_DB_PATH: Final[Path] = _ROOT / "transform" / "argo.duckdb"
_TRAINING_TABLE: Final[str] = "ml_contributor_churn_training"
_PAD_VALUE: Final[float] = 0.0

FEATURE_COLUMNS: Final[list[str]] = [
    "total_events",
    "distinct_repos",
    "active_days",
    "commit_events",
    "pull_request_events",
    "issue_events",
    "comment_events",
    "engagement_events",
    "release_events",
    "weekend_ratio",
    "events_per_active_day",
    "tenure_days",
    "days_since_last_event",
    "velocity_30d",
    "deceleration_score",
    "deceleration_ratio",
]

TARGET_COLUMN: Final[str] = "is_churned"

FEATURE_LABELS: Final[dict[str, str]] = {
    "total_events": "Total Events",
    "distinct_repos": "Distinct Repos",
    "active_days": "Active Days",
    "commit_events": "Commit Events",
    "pull_request_events": "Pull Request Events",
    "issue_events": "Issue Events",
    "comment_events": "Comment Events",
    "engagement_events": "Engagement Events",
    "release_events": "Release Events",
    "weekend_ratio": "Weekend Ratio",
    "events_per_active_day": "Events per Active Day",
    "tenure_days": "Tenure (days)",
    "days_since_last_event": "Days Since Last Event",
    "velocity_30d": "30-Day Velocity",
    "deceleration_score": "Deceleration (raw)",
    "deceleration_ratio": "Deceleration (normalised)",
}


def enforce_schema(frame: pd.DataFrame) -> pd.DataFrame:
    """Project a frame onto the canonical contract, padding what is absent.

    Missing features are inserted as ``0.0`` and the result is reindexed to
    ``FEATURE_COLUMNS`` order, so a training matrix and an inference row are
    positionally identical no matter how their sources were assembled. Padding
    is warned about rather than raised on, because a silently reordered or
    dropped column is the failure mode this function exists to prevent, but a
    genuinely absent one should still be visible in logs.
    """
    missing: list[str] = [column for column in FEATURE_COLUMNS if column not in frame.columns]
    if missing:
        warnings.warn(
            f"Padding {len(missing)} absent feature(s) with {_PAD_VALUE}: {', '.join(missing)}",
            RuntimeWarning,
            stacklevel=2,
        )
        frame = frame.copy()
        for column in missing:
            frame[column] = _PAD_VALUE

    return frame.reindex(columns=FEATURE_COLUMNS).astype("float64")


class ChurnFeatureExtractor:
    """Reads contributor-churn training rows from the DuckDB warehouse."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path: Path = db_path or _DB_PATH

    def extract_features(self) -> pd.DataFrame:
        """Return the training frame: the 16 features plus the churn target."""
        columns: str = ", ".join([*FEATURE_COLUMNS, TARGET_COLUMN])
        connection = duckdb.connect(str(self.db_path), read_only=True)
        try:
            frame: pd.DataFrame = connection.execute(
                f"select {columns} from {_TRAINING_TABLE}"
            ).fetch_df()
        finally:
            connection.close()

        if frame.empty:
            raise ValueError(
                f"{_TRAINING_TABLE} is empty; run etl/land_github_data.py and 'dbt build' first."
            )
        return frame

    def extract_matrix(self) -> tuple[pd.DataFrame, pd.Series]:
        """Return the schema-enforced feature matrix and the target vector."""
        frame: pd.DataFrame = self.extract_features()
        return enforce_schema(frame), frame[TARGET_COLUMN]
