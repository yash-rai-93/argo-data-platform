"""Exercise a running ARGO API, including its warehouse and both models."""

from __future__ import annotations

import argparse

import requests

PREDICTION_INPUT = {
    "total_events": 41,
    "distinct_repos": 2,
    "active_days": 12,
    "commit_events": 18,
    "pull_request_events": 9,
    "issue_events": 7,
    "comment_events": 5,
    "engagement_events": 2,
    "release_events": 0,
    "weekend_ratio": 0.08,
    "events_per_active_day": 3.4,
    "tenure_days": 96,
    "days_since_last_event": 34,
    "velocity_30d": 0.07,
    "deceleration_score": 19,
    "deceleration_ratio": 0.46,
}
_ROUTES = (
    "/health",
    "/api/v1/metrics/executive",
    "/api/v1/metrics/trend",
    "/api/v1/metrics/contributors/sparkline",
    "/api/v1/metrics/throughput/sparkline",
    "/api/v1/metrics/retention/sparkline",
    "/api/v1/metrics/activity/decomposition",
    "/api/v1/metrics/governance/health",
    "/api/v1/customers/risk",
    "/api/v1/predict/model-card",
    "/api/v1/predict/registry",
    "/api/v1/predict/simulate/threshold",
    "/api/v1/intelligence/summary",
)


def main() -> None:
    """Fail on HTTP errors, invalid predictions, or a broken feature contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    base = args.base_url.rstrip("/")
    with requests.Session() as session:
        for path in _ROUTES:
            response = session.get(f"{base}{path}", timeout=args.timeout)
            response.raise_for_status()
            data = response.json()
            if data is None:
                raise RuntimeError(f"Empty JSON response for {path}")
            if path == "/health" and data.get("status") != "ok":
                raise RuntimeError("Health check did not report ok")
            print(f"PASS GET {path}")

        response = session.post(
            f"{base}/api/v1/predict/churn", json=PREDICTION_INPUT, timeout=args.timeout
        )
        response.raise_for_status()
        prediction = response.json()
        if not 0 <= prediction["probability"] <= 1 or prediction["hazard_ratio"] <= 0:
            raise RuntimeError("Prediction returned invalid probability or hazard")
        if not prediction["survival_curve"] or len(prediction["shap_attribution"]) != 16:
            raise RuntimeError("Survival curve or SHAP attribution is incomplete")
        print("PASS POST /api/v1/predict/churn")

        invalid = session.post(f"{base}/api/v1/predict/churn", json={}, timeout=args.timeout)
        if invalid.status_code != 422:
            raise RuntimeError("An invalid prediction request was not rejected")
        print("PASS invalid prediction rejected")


if __name__ == "__main__":
    main()
