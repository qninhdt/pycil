"""Authenticated account and lifecycle contracts."""

from uuid import UUID

from pydantic import BaseModel, Field

from pycil.billing.plans import PlanKey


class AccountDeleteRequest(BaseModel):
    confirmation: str


class AccountExport(BaseModel):
    profile: dict
    collection: list[dict]
    learning: dict
    assistant: dict
    plan: PlanKey
    credit: dict
    periods: list[dict] = Field(default_factory=list)
    usage_events: list[dict] = Field(default_factory=list)


class CurrentUser(BaseModel):
    id: UUID
    email: str
    name: str | None = None
    image: str | None = None


class ViewerRead(CurrentUser):
    """The public projection returned by ``GET /v1/me``."""


class CapabilitiesRead(BaseModel):
    assistant: bool
