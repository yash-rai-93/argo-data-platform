"""Executive-insight generation backed by NVIDIA Nemotron."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_BASE_URL = "https://integrate.api.nvidia.com/v1"
_MODEL = "nvidia/nemotron-3-nano-30b-a3b"


class InsightEngine:
    """Turns Argo metrics into executive narratives via NVIDIA Nemotron."""

    def __init__(self) -> None:
        """Configure an OpenAI-compatible client for the NVIDIA endpoint."""
        self.model = _MODEL
        self.client = OpenAI(
            base_url=_BASE_URL,
            api_key=os.environ.get("NVIDIA_API_KEY"),
        )

    def generate_executive_summary(self, metrics_dict: dict) -> str:
        """Return a concise three-sentence strategic summary of the metrics."""
        system_prompt = (
            "You are a product and revenue strategy advisor for a SaaS platform. "
            "Using the metrics provided, write a concise, three-sentence strategic "
            f"business summary. Metrics: {metrics_dict}"
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Provide the executive summary."},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        return response.choices[0].message.content or ""
