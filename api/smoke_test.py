"""Smoke test the running ARGO API."""

from __future__ import annotations

import requests

_BASE = "http://127.0.0.1:8000"


def _show(label: str, response: requests.Response) -> None:
    """Print the status code and JSON body for a call."""
    print(f"{label}: {response.status_code} {response.json()}")


def main() -> None:
    """Exercise health, executive metrics, and churn prediction."""
    _show("GET /health", requests.get(f"{_BASE}/health", timeout=10))
    _show(
        "GET /api/v1/metrics/executive",
        requests.get(f"{_BASE}/api/v1/metrics/executive", timeout=10),
    )
    _show(
        "POST /api/v1/predict/churn",
        requests.post(
            f"{_BASE}/api/v1/predict/churn",
            json={
                "total_sessions": 5,
                "avg_session_duration": 120.5,
                "account_age_days": 45,
            },
            timeout=10,
        ),
    )


if __name__ == "__main__":
    main()
