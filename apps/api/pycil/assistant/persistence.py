"""Owner-bound assistant persistence primitives shared by routes and runs."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.models import AssistantRun, AssistantThread, RunStatus
from pycil.common.errors import ConflictError, NotFoundError
from pycil.config import settings


def retention_deadline(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + timedelta(days=settings.assistant_retention_days)


async def require_owned_thread(
    session: AsyncSession, thread_id: UUID, owner_id: UUID
) -> AssistantThread:
    """Resolve ownership before any checkpoint, run, history, or action access."""
    thread = await session.get(AssistantThread, thread_id)
    if thread is None or thread.owner_id != owner_id or thread.status != "active":
        raise NotFoundError("assistant_thread_not_found")
    return thread


async def create_or_load_run(
    session: AsyncSession,
    *,
    thread_id: UUID,
    owner_id: UUID,
    client_message_id: UUID,
) -> tuple[AssistantRun, bool]:
    """Return a replay-safe run; ``created`` is true only for a new execution."""
    # Serialize all decisions for a thread. This closes the read-then-insert
    # race between different client messages without relying on Redis alone.
    thread = await session.get(AssistantThread, thread_id, with_for_update=True)
    if thread is None or thread.owner_id != owner_id or thread.status != "active":
        raise NotFoundError("assistant_thread_not_found")
    existing = await session.scalar(
        select(AssistantRun).where(
            AssistantRun.owner_id == owner_id,
            AssistantRun.client_message_id == client_message_id,
        )
    )
    if existing is not None:
        if existing.thread_id != thread_id:
            raise ConflictError("client_message_id_reused")
        return existing, False
    active = await session.scalar(
        select(AssistantRun).where(
            AssistantRun.thread_id == thread_id,
            AssistantRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING, RunStatus.INTERRUPTED]),
        )
    )
    if active is not None:
        raise ConflictError("assistant_thread_run_active")
    run = AssistantRun(
        thread_id=thread_id,
        owner_id=owner_id,
        client_message_id=client_message_id,
        status=RunStatus.PENDING,
    )
    session.add(run)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await session.scalar(
            select(AssistantRun).where(
                AssistantRun.owner_id == owner_id,
                AssistantRun.client_message_id == client_message_id,
            )
        )
        if existing is not None and existing.thread_id == thread_id:
            return existing, False
        raise ConflictError("assistant_run_create_conflict") from exc
    await session.refresh(run)
    return run, True


async def revalidate_actor(session: AsyncSession, user_id: UUID, token_version: int) -> None:
    """Re-read authoritative account state immediately before a mutation/resume."""
    from pycil.auth.models import User
    from pycil.common.errors import ForbiddenError

    user = await session.get(User, user_id)
    if user is None or user.token_version != token_version:
        raise ForbiddenError("assistant_actor_revoked", code="assistant_actor_revoked")
