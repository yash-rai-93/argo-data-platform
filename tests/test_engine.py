"""Invariant tests for the stateful event generator."""

from __future__ import annotations

import json
from datetime import datetime
from itertools import groupby

import pytest

from generator.engine import DataGenerator

SEED = 42
N_USERS = 25


@pytest.fixture
def events() -> list[dict]:
    return [json.loads(line) for line in DataGenerator(seed=SEED).generate(N_USERS)]


def _by_user(events: list[dict]) -> groupby[str, dict]:
    # Journeys are emitted contiguously, so a straight groupby is sufficient.
    return groupby(events, key=lambda e: e["user_id"])


def test_determinism() -> None:
    a = list(DataGenerator(seed=SEED).generate(N_USERS))
    b = list(DataGenerator(seed=SEED).generate(N_USERS))
    assert a == b


def test_identity_persistence(events: list[dict]) -> None:
    for _, group in _by_user(events):
        rows = list(group)
        for field in ("account_id", "platform", "device_type"):
            assert len({row[field] for row in rows}) == 1


def test_temporal_ordering(events: list[dict]) -> None:
    for _, group in _by_user(events):
        rows = list(group)
        assert rows[0]["event_name"] == "user_registered"
        timestamps = [datetime.fromisoformat(row["event_timestamp"]) for row in rows]
        assert all(a < b for a, b in zip(timestamps, timestamps[1:], strict=False))
