"""Pydantic models for Argo's Canonical Event Model.

Every emitted event carries the shared envelope defined in `BaseEvent`.
Family subclasses constrain `event_name` to the taxonomy in `Argo.txt`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DeviceType(StrEnum):
    DESKTOP = "Desktop"
    MOBILE = "Mobile"
    TABLET = "Tablet"


class Platform(StrEnum):
    WEB = "Web"
    IOS = "iOS"
    ANDROID = "Android"


class SubscriptionPlan(StrEnum):
    FREE = "Free"
    PRO = "Pro"
    ENTERPRISE = "Enterprise"


class AcquisitionName(StrEnum):
    USER_REGISTERED = "user_registered"
    USER_INVITED = "user_invited"
    WORKSPACE_CREATED = "workspace_created"
    MARKETING_SIGNUP = "marketing_signup"
    REFERRAL_SIGNUP = "referral_signup"


class ActivationName(StrEnum):
    PROFILE_COMPLETED = "profile_completed"
    FIRST_PROJECT_CREATED = "first_project_created"
    FIRST_TEAM_MEMBER_INVITED = "first_team_member_invited"
    FIRST_FILE_UPLOADED = "first_file_uploaded"
    FIRST_DASHBOARD_CREATED = "first_dashboard_created"
    FIRST_REPORT_GENERATED = "first_report_generated"


class EngagementName(StrEnum):
    LOGIN = "login"
    LOGOUT = "logout"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    FEATURE_CLICKED = "feature_clicked"
    SEARCH_PERFORMED = "search_performed"
    REPORT_VIEWED = "report_viewed"
    DASHBOARD_VIEWED = "dashboard_viewed"
    EXPORT_GENERATED = "export_generated"


class CollaborationName(StrEnum):
    MEMBER_INVITED = "member_invited"
    MEMBER_JOINED = "member_joined"
    COMMENT_ADDED = "comment_added"
    PROJECT_SHARED = "project_shared"
    WORKSPACE_ACTIVITY = "workspace_activity"


class MonetizationName(StrEnum):
    TRIAL_STARTED = "trial_started"
    TRIAL_ENDED = "trial_ended"
    SUBSCRIPTION_STARTED = "subscription_started"
    SUBSCRIPTION_RENEWED = "subscription_renewed"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"
    PLAN_UPGRADED = "plan_upgraded"
    PLAN_DOWNGRADED = "plan_downgraded"


class SupportName(StrEnum):
    TICKET_CREATED = "ticket_created"
    TICKET_CLOSED = "ticket_closed"
    HELP_CENTER_ACCESSED = "help_center_accessed"
    FEEDBACK_SUBMITTED = "feedback_submitted"


class BaseEvent(BaseModel):
    """Shared envelope for every Argo event."""

    model_config = ConfigDict(frozen=True, use_enum_values=True)

    event_id: UUID = Field(default_factory=uuid4)
    event_name: str
    event_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    user_id: str
    account_id: str
    session_id: str
    device_type: DeviceType
    platform: Platform
    country: str
    region: str
    subscription_plan: SubscriptionPlan
    feature_name: str | None = None
    event_source: str
    event_version: str = "1.0"


class AcquisitionEvent(BaseEvent):
    event_name: AcquisitionName
    event_source: str = "acquisition"


class ActivationEvent(BaseEvent):
    event_name: ActivationName
    event_source: str = "activation"


class EngagementEvent(BaseEvent):
    event_name: EngagementName
    event_source: str = "engagement"


class CollaborationEvent(BaseEvent):
    event_name: CollaborationName
    event_source: str = "collaboration"


class MonetizationEvent(BaseEvent):
    event_name: MonetizationName
    event_source: str = "monetization"


class SupportEvent(BaseEvent):
    event_name: SupportName
    event_source: str = "support"
