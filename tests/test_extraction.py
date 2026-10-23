"""Guard against paid uncapped queries and writes during dry runs."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest

from etl import land_github_data as extraction


@pytest.mark.parametrize("limit", [None, 0, -1])
def test_uncapped_execution_never_creates_client(limit: int | None) -> None:
    with patch.object(extraction.bigquery, "Client") as client:
        with pytest.raises(ValueError, match="positive maximum_bytes_billed"):
            extraction.run_bigquery_extract(
                "select 1", project="argo-test", maximum_bytes_billed=limit
            )
        client.assert_not_called()


def test_dry_run_does_not_download_or_land(capsys: pytest.CaptureFixture[str]) -> None:
    job = MagicMock(total_bytes_processed=2048)
    with patch.object(extraction.bigquery, "Client") as client:
        query_client = client.return_value.__enter__.return_value
        query_client.query.return_value = job
        result = extraction.run_bigquery_extract(
            "select 1", project="argo-test", location="US", dry_run=True
        )
        config = query_client.query.call_args.kwargs["job_config"]
        assert config.dry_run is True
        assert config.use_query_cache is False
        job.to_arrow.assert_not_called()
    assert result is None
    assert "2,048 bytes" in capsys.readouterr().out


def test_execution_sends_the_explicit_billing_limit() -> None:
    table = pa.table({"event_id": ["test-event"]})
    job = MagicMock(total_bytes_processed=1024)
    job.to_arrow.return_value = table
    with patch.object(extraction.bigquery, "Client") as client:
        query_client = client.return_value.__enter__.return_value
        query_client.query.return_value = job
        result = extraction.run_bigquery_extract(
            "select 1", project="argo-test", maximum_bytes_billed=4096
        )
        assert query_client.query.call_args.kwargs["job_config"].maximum_bytes_billed == 4096
    assert result is table


def test_empty_extract_cannot_replace_the_existing_warehouse() -> None:
    with patch.object(extraction.duckdb, "connect") as connect:
        with pytest.raises(ValueError, match="existing warehouse was not changed"):
            extraction.land_to_duckdb(pa.table({"event_id": []}))
        connect.assert_not_called()


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_invalid_billing_limits_are_rejected(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        extraction.positive_bytes(value)
