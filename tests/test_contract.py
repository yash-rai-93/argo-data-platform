"""Schema-parity tests for the 16-feature contract.

The failure this guards against is silent and expensive: a feature is added to
``FEATURE_COLUMNS`` and the model is retrained, but the Pydantic request schema
is not updated. Inference then pads the missing column with 0.0, the API keeps
returning 200, and every prediction is quietly wrong.

``api.routers.predict`` already asserts parity at import time, so importing it
is itself part of the test. The explicit assertions below exist so a failure
reports *which* field drifted rather than just refusing to import.

No warehouse is touched. Nothing here opens a DuckDB connection, reads
``transform/argo.duckdb``, or loads a model artifact. Model and explainer loading
is behind ``lru_cache`` and only fires on the first request.
"""

from __future__ import annotations

import pandas as pd
import pytest

from api.routers.predict import ChurnPredictionRequest
from ml.feature_extractor import FEATURE_COLUMNS, FEATURE_LABELS, TARGET_COLUMNS, enforce_schema


def test_request_schema_matches_feature_columns() -> None:
    """Pydantic fields must equal FEATURE_COLUMNS in name, count, and order."""
    assert list(ChurnPredictionRequest.model_fields) == FEATURE_COLUMNS


def test_feature_columns_are_unique() -> None:
    """A duplicated feature would silently shrink the matrix on reindex."""
    assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))


def test_targets_are_not_features() -> None:
    """duration and event are labels; either one as a feature is total leakage."""
    assert not set(TARGET_COLUMNS) & set(FEATURE_COLUMNS)
    assert "is_churned" not in FEATURE_COLUMNS


def test_every_feature_has_a_display_label() -> None:
    """FEATURE_LABELS backs the SHAP chart and model card; gaps render raw names."""
    assert set(FEATURE_LABELS) == set(FEATURE_COLUMNS)


def test_enforce_schema_drops_the_split_key() -> None:
    """first_event_at orders the chronological split and must never be a feature.

    Leaving it in would hand the model the very variable the holdout is defined
    by, which is the most direct leak available in this pipeline.
    """
    frame = pd.DataFrame([dict.fromkeys([*FEATURE_COLUMNS, "first_event_at"], 1.0)])
    assert "first_event_at" not in enforce_schema(frame).columns


def test_enforce_schema_reorders_to_canonical_order() -> None:
    """Positional identity matters: XGBoost consumes columns by position."""
    shuffled = pd.DataFrame([dict.fromkeys(reversed(FEATURE_COLUMNS), 1.0)])
    assert list(enforce_schema(shuffled).columns) == FEATURE_COLUMNS


def test_enforce_schema_pads_absent_features_and_warns() -> None:
    """Padding keeps inference alive, but it must never happen silently."""
    partial = pd.DataFrame([{FEATURE_COLUMNS[0]: 5.0}])
    with pytest.warns(RuntimeWarning, match="Padding"):
        padded = enforce_schema(partial)

    assert list(padded.columns) == FEATURE_COLUMNS
    assert padded.iloc[0][FEATURE_COLUMNS[1]] == 0.0
    assert str(padded.dtypes.unique()[0]) == "float64"


def test_deployment_smoke_payload_is_valid() -> None:
    """The deployed smoke check must exercise the full current request contract."""
    from api.smoke_test import PREDICTION_INPUT

    assert set(PREDICTION_INPUT) == set(FEATURE_COLUMNS)
    ChurnPredictionRequest.model_validate(PREDICTION_INPUT)
