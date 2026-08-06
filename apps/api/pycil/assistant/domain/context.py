"""Immutable dependencies injected into LangChain tools at invocation time."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AssistantContext:
    user_id: UUID
    token_version: int
    # Present only while continuing an approved HITL action.  Tools use this
    # durable idempotency key instead of relying on an SSE connection.
    action_id: UUID | None = None
