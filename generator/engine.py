"""Stateful synthetic-event generator for Argo.

Simulates a realistic SaaS lifecycle per user
(Anonymous -> Registered -> Activated -> Engaged -> Churned/Retained),
persisting identity across an ordered event sequence. Deterministic given a seed.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import UTC, timedelta

from faker import Faker

from generator.schemas import (
    AcquisitionEvent,
    AcquisitionName,
    ActivationEvent,
    ActivationName,
    BaseEvent,
    CollaborationEvent,
    CollaborationName,
    DeviceType,
    EngagementEvent,
    EngagementName,
    MonetizationEvent,
    MonetizationName,
    Platform,
    SubscriptionPlan,
    SupportEvent,
    SupportName,
)

_FEATURES = ("dashboards", "reports", "search", "exports", "integrations", "settings")
_COLLAB_EVENTS = (
    CollaborationName.WORKSPACE_ACTIVITY,
    CollaborationName.PROJECT_SHARED,
    CollaborationName.MEMBER_INVITED,
)
_PLAN_WEIGHTS = (0.7, 0.22, 0.08)  # Free, Pro, Enterprise
_ACTIVATION_RATE = 0.7
_RETENTION_RATE = 0.7
_COLLAB_RATE = 0.3  # chance a feature click spawns a collaboration event
_SUPPORT_RATE = 0.1  # chance a day includes a support ticket
_TRIAL_DAYS = 14


class DataGenerator:
    """Produces JSON event streams that follow the canonical lifecycle."""

    def __init__(self, seed: int | None = None) -> None:
        self.faker = Faker()
        self.rng = random.Random(seed)
        if seed is not None:
            self.faker.seed_instance(seed)

    def _context(self) -> dict[str, object]:
        """Identity + attributes that persist across one user's journey."""
        return {
            "user_id": str(self.faker.uuid4()),
            "account_id": str(self.faker.uuid4()),
            "device_type": self.rng.choice(list(DeviceType)),
            "platform": self.rng.choice(list(Platform)),
            "country": self.faker.country_code(),
            "region": self.faker.state(),
            "subscription_plan": self.rng.choices(list(SubscriptionPlan), weights=_PLAN_WEIGHTS)[0],
        }

    def _journey(self, days: int) -> list[BaseEvent]:
        ctx = self._context()
        clock = self.faker.date_time_between(start_date=f"-{days}d", end_date="now", tzinfo=UTC)
        session_id = str(self.faker.uuid4())
        events: list[BaseEvent] = []

        def envelope(**extra: object) -> dict[str, object]:
            return {
                "event_id": self.faker.uuid4(),  # seeded, so the stream is reproducible
                "user_id": ctx["user_id"],
                "account_id": ctx["account_id"],
                "session_id": session_id,
                "device_type": ctx["device_type"],
                "platform": ctx["platform"],
                "country": ctx["country"],
                "region": ctx["region"],
                "subscription_plan": ctx["subscription_plan"],
                **extra,
            }

        def emit(cls: type[BaseEvent], name: object, **extra: object) -> None:
            # `clock` is always advanced before each call, so events stay strictly ordered.
            events.append(cls(event_name=name, event_timestamp=clock, **envelope(**extra)))

        # Registered: anchors the sequence; nothing downstream precedes it.
        clock += timedelta(minutes=self.rng.randint(0, 60))
        emit(AcquisitionEvent, AcquisitionName.USER_REGISTERED)
        trial_expiry = clock + timedelta(days=_TRIAL_DAYS)

        # Trial starts near registration.
        clock += timedelta(minutes=self.rng.randint(1, 30))
        emit(MonetizationEvent, MonetizationName.TRIAL_STARTED)

        activated = self.rng.random() < _ACTIVATION_RATE
        if not activated:
            clock = max(clock, trial_expiry) + timedelta(minutes=self.rng.randint(1, 60))
            emit(MonetizationEvent, MonetizationName.TRIAL_ENDED)
            return events

        # Activated: an ordered prefix of the activation funnel (natural drop-off).
        for name in list(ActivationName)[: self.rng.randint(1, len(ActivationName))]:
            clock += timedelta(minutes=self.rng.randint(1, 120))
            emit(ActivationEvent, name)

        # Engaged: retained users span past the trial; churned users fade fast.
        retained = self.rng.random() < _RETENTION_RATE
        active_days = self.rng.randint(_TRIAL_DAYS, 60) if retained else self.rng.randint(0, 2)
        converted = False
        for day_index in range(active_days):
            clock += timedelta(days=1, minutes=self.rng.randint(0, 240))

            # Retained past the trial -> convert to a paid subscription.
            if retained and not converted and day_index + 1 >= _TRIAL_DAYS:
                clock += timedelta(minutes=self.rng.randint(1, 30))
                emit(MonetizationEvent, MonetizationName.SUBSCRIPTION_STARTED)
                clock += timedelta(seconds=self.rng.randint(1, 59))
                emit(MonetizationEvent, MonetizationName.PAYMENT_COMPLETED)
                converted = True

            session_id = str(self.faker.uuid4())
            clock += timedelta(seconds=self.rng.randint(1, 59))
            emit(EngagementEvent, EngagementName.LOGIN)
            clock += timedelta(seconds=self.rng.randint(1, 59))
            emit(EngagementEvent, EngagementName.SESSION_STARTED)

            for _ in range(self.rng.randint(1, 8)):
                clock += timedelta(minutes=self.rng.randint(1, 30))
                emit(
                    EngagementEvent,
                    EngagementName.FEATURE_CLICKED,
                    feature_name=self.rng.choice(_FEATURES),
                )
                if self.rng.random() < _COLLAB_RATE:
                    clock += timedelta(seconds=self.rng.randint(1, 59))
                    emit(CollaborationEvent, self.rng.choice(_COLLAB_EVENTS))

            clock += timedelta(minutes=self.rng.randint(1, 20))
            emit(EngagementEvent, EngagementName.SESSION_ENDED)
            clock += timedelta(seconds=self.rng.randint(1, 59))
            emit(EngagementEvent, EngagementName.LOGOUT)

            # A support ticket may be opened and later resolved within the day.
            if self.rng.random() < _SUPPORT_RATE:
                clock += timedelta(minutes=self.rng.randint(1, 30))
                emit(SupportEvent, SupportName.TICKET_CREATED)
                clock += timedelta(minutes=self.rng.randint(5, 120))
                emit(SupportEvent, SupportName.TICKET_CLOSED)

        # Churned before converting -> the trial simply expires.
        if not retained:
            clock = max(clock, trial_expiry) + timedelta(minutes=self.rng.randint(1, 60))
            emit(MonetizationEvent, MonetizationName.TRIAL_ENDED)

        return events

    def generate(self, n_users: int, days: int = 90) -> Iterator[str]:
        """Yield each event as a JSON string, ordered per user journey."""
        for _ in range(n_users):
            for event in self._journey(days):
                yield event.model_dump_json()
