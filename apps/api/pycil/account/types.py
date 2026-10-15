"""Typed data structures and dictionaries for the account domain."""

from datetime import datetime
from typing import TypedDict
from uuid import UUID

from pycil.account.plans import Plan


class AllowanceData(TypedDict):
    period_start: datetime
    period_end: datetime
    allowance_units: int
    used_units: int
    remaining_units: int


class PublicProfileData(TypedDict):
    id: UUID
    display_name: str | None
    handle: str | None
    bio: str | None
    joined_at: datetime
    published_node_id: UUID


class ProfileData(PublicProfileData):
    learning_options: dict[str, object]
    plan: Plan
    settings: dict[str, object]
    effective_learning: dict[str, object] | None
    learning_restriction: str | None
    library_node_id: UUID
    personal_node_id: UUID


class UserSettingsDict(TypedDict, total=False):
    locale: str
    timezone: str
    translation_language: str
    learning: dict[str, object]
    assistant: dict[str, object]
