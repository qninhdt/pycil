"""Owner-bound assistant thread persistence.

Conversation state lives in the LangGraph checkpointer, not here. This module owns
only what the checkpointer cannot know: which learner a thread belongs to, and
when its retained history expires.

The active-turn bound is a Redis lease (see :mod:`pycil.assistant.application.
turn_lease`), not a row here, so nothing in this module serializes turns.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.infra.models import AssistantThread
from pycil.auth.models import User
from pycil.common.errors import ForbiddenError, NotFoundError
from pycil.config import settings


def retention_deadline(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + timedelta(days=settings.assistant_retention_days)


async def require_owned_thread(
    session: AsyncSession, thread_id: UUID, owner_id: UUID
) -> AssistantThread:
    """The thread, or a 404 — never another learner's thread.

    A missing thread and someone else's thread answer identically, so a caller
    cannot use this to discover which thread ids exist.
    """
    thread = await session.get(AssistantThread, thread_id)
    if thread is None or thread.owner_id != owner_id or thread.status != "active":
        raise NotFoundError("assistant_thread_not_found")
    return thread


async def refresh_retention(session: AsyncSession, thread: AssistantThread) -> None:
    thread.retention_deadline = retention_deadline()
    await session.commit()


async def touch_thread(session: AsyncSession, thread: AssistantThread) -> None:
    """Mark a thread as used, so its retained history does not expire mid-use."""
    thread.retention_deadline = retention_deadline()
    thread.updated_at = datetime.now(UTC)
    await session.commit()


async def revalidate_actor(session: AsyncSession, user_id: UUID) -> None:
    """Refuse work for an account that no longer exists.

    An approved tool call may be resumed long after it was raised, so the account
    is re-read at the moment of the write. Clerk owns session validity; this
    checks only that the owner row is still there, which is what stops a deleted
    account's pending approvals from executing.
    """
    user = await session.get(User, user_id)
    if user is None:
        raise ForbiddenError("assistant_actor_revoked", code="assistant_actor_revoked")
