"""UI projections of native messages and persisted approval state."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from ag_ui.core import Message
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateConversation(Strict):
    title: str | None = Field(default=None, max_length=255)


class AssistantModel(Strict):
    id: str
    name: str
    vision: bool
    efforts: list[str]


class ConversationView(Strict):
    id: UUID
    user_id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationPage(Strict):
    conversations: list[ConversationView]
    next_cursor: str | None


class ApprovalAction(Strict):
    name: str
    args: dict[str, Any]
    description: str | None = None


class ApprovalConfig(Strict):
    action_name: str
    allowed_decisions: list[Literal["approve", "reject"]]


class PendingApproval(Strict):
    interrupt_id: str
    action_requests: list[ApprovalAction]
    review_configs: list[ApprovalConfig]


class ConversationState(Strict):
    messages: list[Message]
    pending_approvals: list[PendingApproval]


class ConversationDetails(ConversationView):
    state: ConversationState
