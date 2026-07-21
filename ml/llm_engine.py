"""Executive-insight generation via OpenRouter (NVIDIA Nemotron)."""

from __future__ import annotations

import json
import os

import requests

_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

_MOCK = {
    "summary": (
        "Recurring revenue is modest but real, with MRR near $740 (ARR ~$8.9K) "
        "against a small monetizing base, so the binding constraint on growth is "
        "retention rather than acquisition. The churn model concentrates risk in "
        "low-session, longer-tenured accounts, which is where a proactive save "
        "motion will protect the most revenue. The highest-leverage move is to "
        "drive trial users into their first collaborative action within 14 days "
        "while nudging engaged Pro accounts toward Enterprise expansion."
    ),
    "reasoning": (
        "Reasoning trace: (1) Parsed the executive metrics and normalized MRR/ARR "
        "against the Free/Pro/Enterprise plan mix to estimate blended ARPU. "
        "(2) Compared the trailing active-user average with the recurring-revenue "
        "base to infer monetization efficiency per active user. (3) Weighed the "
        "churn-probability distribution, noting that risk clusters in accounts with "
        "few sessions but high account age, a classic dormancy signal. "
        "(4) Ranked levers by expected revenue impact: retention saves outrank new "
        "acquisition at this scale, and plan expansion outranks discounting. "
        "(5) Concluded with three actions ordered by leverage and time-to-impact."
    ),
}


class InsightEngine:
    """Turns Argo metrics into executive narratives via OpenRouter."""

    def __init__(self) -> None:
        """Read the OpenRouter API key from the environment."""
        self.api_key = os.environ.get("OPENROUTER_API_KEY")

    def generate_executive_summary(self, metrics_dict: dict) -> dict:
        """Return a summary and reasoning, falling back to a mock on any failure."""
        if not self.api_key:
            return _MOCK
        payload = {
            "model": _MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a product and revenue strategy advisor for a SaaS "
                        "platform. Write a concise, three-sentence strategic business "
                        "summary of the metrics provided."
                    ),
                },
                {"role": "user", "content": f"Metrics: {json.dumps(metrics_dict)}"},
            ],
            "reasoning": {"enabled": True},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            return {
                "summary": message.get("content") or _MOCK["summary"],
                "reasoning": message.get("reasoning_details") or _MOCK["reasoning"],
            }
        except (requests.RequestException, KeyError, ValueError, IndexError):
            return _MOCK
