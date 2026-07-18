"""Contract tests for the canonical event schemas."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from generator.schemas import AcquisitionEvent, BaseEvent

_ENVELOPE = {
    "event_name": "user_registered",
    "user_id": "u1",
    "account_id": "a1",
    "session_id": "s1",
    "device_type": "Desktop",
    "platform": "Web",
    "country": "US",
    "region": "CA",
    "subscription_plan": "Free",
    "event_source": "acquisition",
}


def test_event_id_is_uuid4() -> None:
    event = BaseEvent(**_ENVELOPE)
    assert event.event_id.version == 4


def test_event_timestamp_defaults_to_utc() -> None:
    event = BaseEvent(**_ENVELOPE)
    assert event.event_timestamp.tzinfo is not None
    assert event.event_timestamp.utcoffset() == datetime.now(UTC).utcoffset()


def test_child_rejects_invalid_event_name() -> None:
    with pytest.raises(ValidationError):
        AcquisitionEvent(**{**_ENVELOPE, "event_name": "not_a_real_event"})


def test_child_accepts_valid_event_name() -> None:
    event = AcquisitionEvent(**_ENVELOPE)
    assert event.event_name == "user_registered"
