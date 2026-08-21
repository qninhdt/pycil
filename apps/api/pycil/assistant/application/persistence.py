"""Owner-bound assistant persistence primitives shared by routes and runs."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.infra.models import (
    AssistantRun,
    AssistantRunEvent,
    AssistantThread,
    RunStatus,
)
from pycil.auth.models import User
from pycil.common.errors import ConflictError, ForbiddenError, NotFoundError
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


async def refresh_retention(session: AsyncSession, thread: AssistantThread) -> None:
    """Extend the thread's retention window on each authenticated access."""
    thread.retention_deadline = retention_deadline()
    await session.commit()


async def require_owned_run(
    session: AsyncSession, *, run_id: UUID, thread_id: UUID, owner_id: UUID
) -> AssistantRun:
    """Resolve a run the owner may read, scoped to the thread it belongs to."""
    run = await session.get(AssistantRun, run_id)
    if run is None or run.thread_id != thread_id or run.owner_id != owner_id:
        raise NotFoundError("assistant_run_not_found")
    return run


async def thread_events(session: AsyncSession, thread_id: UUID) -> list[AssistantRunEvent]:
    """Every event of a thread's transcript, ordered across all of its runs."""
    events = await session.execute(
        select(AssistantRunEvent)
        .join(AssistantRun, AssistantRun.id == AssistantRunEvent.run_id)
        .where(AssistantRun.thread_id == thread_id)
        .order_by(AssistantRunEvent.created_at, AssistantRunEvent.sequence)
    )
    return list(events.scalars())


async def run_events(
    session: AsyncSession, run_id: UUID, after: int = 0
) -> list[AssistantRunEvent]:
    """Events of one run after an exclusive sequence cursor, for stream recovery."""
    events = await session.scalars(
        select(AssistantRunEvent)
        .where(AssistantRunEvent.run_id == run_id, AssistantRunEvent.sequence > after)
        .order_by(AssistantRunEvent.sequence)
    )
    return list(events)


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
    user = await session.get(User, user_id)
    if user is None or user.token_version != token_version:
        raise ForbiddenError("assistant_actor_revoked", code="assistant_actor_revoked")
