"""Ensure the no-key deployment describes actual contributor metrics."""

from __future__ import annotations

from unittest.mock import patch

from ml.llm_engine import InsightEngine

_METRICS = {"active_contributors": 1234, "pr_throughput": 56, "retention_rate": 0.25}


def test_no_key_summary_uses_observed_metrics(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    with patch("ml.llm_engine.requests.post") as post:
        result = InsightEngine().generate_executive_summary(_METRICS)
        post.assert_not_called()
    assert "1,234" in result["summary"]
    assert "56" in result["summary"]
    assert "25.0%" in result["summary"]
    assert "historical" in result["summary"].lower()
    assert "revenue" not in result["summary"].lower()
    assert result["source"] == "template"


def test_key_without_explicit_model_makes_no_provider_call(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    with patch("ml.llm_engine.requests.post") as post:
        assert InsightEngine().generate_executive_summary(_METRICS)["source"] == "template"
        post.assert_not_called()


def test_provider_failure_returns_measured_summary(monkeypatch) -> None:
    import requests

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setenv("OPENROUTER_MODEL", "explicit-test-model")
    with patch("ml.llm_engine.requests.post", side_effect=requests.ConnectionError):
        result = InsightEngine().generate_executive_summary(_METRICS)
    assert result["source"] == "template"
    assert "25.0%" in result["summary"]
