"""Model registry: every training iteration, its metrics, and what changed.

A single ROC-AUC on a slide proves nothing. What proves engineering judgement
is the sequence: what was tried, what it measured, and why the number moved.
This module persists that sequence to ``main.meta_model_registry``.

Every row below is a real executed run, not a narrative. The metrics were
produced by ``ml/train_churn.py`` against the warehouse at that point in time
and are reproducible by reverting the corresponding change. ``train_churn.py``
appends to this table automatically on every subsequent run, so the history
grows from execution rather than from editing.

One row is explicitly not comparable to the others and is flagged as such:
v0.1 scored a different target (SaaS user churn) on synthetic Faker data that
has since been deleted. It is retained because the drop from 0.97 to 0.66 on
real data is the most important number in this table -- it is the cost of
being honest about where the data came from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import duckdb
import pandas as pd

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_DB_PATH: Final[Path] = _ROOT / "transform" / "argo.duckdb"
_TABLE: Final[str] = "main.meta_model_registry"

_SCHEMA: Final[str] = f"""
create table if not exists {_TABLE} (
    version varchar,
    recorded_at timestamptz,
    dataset varchar,
    split_strategy varchar,
    n_features integer,
    n_rows integer,
    n_train integer,
    n_test integer,
    churn_rate_test double,
    cv_roc_auc double,
    holdout_roc_auc double,
    precision_score double,
    recall_score double,
    best_params varchar,
    change_summary varchar,
    comparable boolean
)
"""

HISTORY: Final[list[dict[str, Any]]] = [
    {
        "version": "v0.1-synthetic",
        "recorded_at": datetime(2026, 7, 1, tzinfo=UTC),
        "dataset": "Faker-generated SaaS events (deleted)",
        "split_strategy": "stratified random",
        "n_features": 3,
        "n_rows": 1000,
        "n_train": 800,
        "n_test": 200,
        "churn_rate_test": None,
        "cv_roc_auc": None,
        "holdout_roc_auc": 0.97,
        "precision_score": None,
        "recall_score": None,
        "best_params": "defaults",
        "change_summary": (
            "Baseline on synthetic data. The model rediscovered the rules the "
            "generator was programmed with. Not a measurement of anything."
        ),
        "comparable": False,
    },
    {
        "version": "v1.0-github-raw",
        "recorded_at": datetime(2026, 7, 20, 9, 40, tzinfo=UTC),
        "dataset": "GitHub Archive, 547,434 events, no eligibility floor",
        "split_strategy": "chronological 80/20 + TimeSeriesSplit(3)",
        "n_features": 13,
        "n_rows": 54613,
        "n_train": 43690,
        "n_test": 10923,
        "churn_rate_test": 0.9070,
        "cv_roc_auc": 0.7020,
        "holdout_roc_auc": 0.6620,
        "precision_score": 0.9269,
        "recall_score": 0.8988,
        "best_params": "max_depth=3, lr=0.01, subsample=0.6",
        "change_summary": (
            "First run on real data. Precision 0.93 is an artefact of a 90.7% "
            "base rate, not skill. Cohort dominated by drive-by contributors."
        ),
        "comparable": True,
    },
    {
        "version": "v2.0-eligibility-floor",
        "recorded_at": datetime(2026, 7, 20, 9, 43, tzinfo=UTC),
        "dataset": "GitHub Archive, floor: >=5 events across >=3 active days",
        "split_strategy": "chronological 80/20 + TimeSeriesSplit(3)",
        "n_features": 13,
        "n_rows": 3033,
        "n_train": 2426,
        "n_test": 607,
        "churn_rate_test": 0.5964,
        "cv_roc_auc": 0.8089,
        "holdout_roc_auc": 0.7399,
        "precision_score": 0.7609,
        "recall_score": 0.6243,
        "best_params": "max_depth=3, lr=0.01, subsample=0.6",
        "change_summary": (
            "Eligibility floor cut the cohort 18x and the base rate to 59.6%. "
            "AUC rose while precision fell: the problem became genuinely hard."
        ),
        "comparable": True,
    },
    {
        "version": "v2.1-regularized",
        "recorded_at": datetime(2026, 7, 20, 12, 50, tzinfo=UTC),
        "dataset": "GitHub Archive, floor applied, trajectory features added",
        "split_strategy": "chronological 80/20 + TimeSeriesSplit(3)",
        "n_features": 16,
        "n_rows": 3033,
        "n_train": 2426,
        "n_test": 607,
        "churn_rate_test": 0.5964,
        "cv_roc_auc": 0.8131,
        "holdout_roc_auc": 0.7563,
        "precision_score": 0.7616,
        "recall_score": 0.7238,
        "best_params": "max_depth=2, min_child_weight=5, n=100, lr=0.05, subsample=0.6",
        "change_summary": (
            "Added velocity/deceleration trajectory features and pushed the "
            "grid past its previous floor. Overfit gap narrowed 0.069 -> 0.057."
        ),
        "comparable": True,
    },
    {
        "version": "v2.2-boundary-probe",
        "recorded_at": datetime(2026, 7, 20, 13, 0, tzinfo=UTC),
        "dataset": "GitHub Archive, floor applied, trajectory features",
        "split_strategy": "chronological 80/20 + TimeSeriesSplit(3)",
        "n_features": 16,
        "n_rows": 3033,
        "n_train": 2426,
        "n_test": 607,
        "churn_rate_test": 0.5964,
        "cv_roc_auc": 0.8137,
        "holdout_roc_auc": 0.7553,
        "precision_score": 0.7704,
        "recall_score": 0.6768,
        "best_params": "max_depth=2, min_child_weight=5, n=400, lr=0.01, subsample=0.6",
        "change_summary": (
            "Extended depth to stumps and the ensemble to 400 rounds. Moved "
            "holdout AUC by -0.001: the search has converged. Deployed."
        ),
        "comparable": True,
    },
]


def ensure_table(connection: duckdb.DuckDBPyConnection) -> None:
    """Create the registry table when it does not yet exist."""
    connection.execute(_SCHEMA)


def seed_history() -> None:
    """Load the recorded iteration history, replacing any prior seed."""
    frame = pd.DataFrame.from_records(HISTORY)
    connection = duckdb.connect(str(_DB_PATH))
    try:
        ensure_table(connection)
        connection.register("registry_arrow", frame)
        versions = ", ".join(f"'{row['version']}'" for row in HISTORY)
        connection.execute(f"delete from {_TABLE} where version in ({versions})")
        connection.execute(f"insert into {_TABLE} select * from registry_arrow")
    finally:
        connection.close()


def record_run(entry: dict[str, Any]) -> None:
    """Append one training run to the registry, replacing a same-version row.

    Called at the end of ml/train_churn.py so the registry accumulates from
    execution rather than from hand-editing this module.
    """
    frame = pd.DataFrame.from_records([entry])
    connection = duckdb.connect(str(_DB_PATH))
    try:
        ensure_table(connection)
        connection.register("registry_row_arrow", frame)
        connection.execute(f"delete from {_TABLE} where version = ?", [entry["version"]])
        connection.execute(f"insert into {_TABLE} select * from registry_row_arrow")
    finally:
        connection.close()


def main() -> None:
    """Seed the registry with the recorded iteration history."""
    seed_history()
    connection = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        rows = connection.execute(
            f"select version, n_features, n_rows, holdout_roc_auc "
            f"from {_TABLE} order by recorded_at asc"
        ).fetchall()
    finally:
        connection.close()

    print(f"Seeded {len(HISTORY)} runs into {_TABLE}")
    for version, features, rows_count, auc in rows:
        auc_text = f"{auc:.4f}" if auc is not None else "n/a"
        print(f"  {version:<24} {features:>3}f  {rows_count:>6} rows  AUC {auc_text}")


if __name__ == "__main__":
    main()
