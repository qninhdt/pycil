"""Thread-level lifecycle: creation, listing, and deletion with full history."""

from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.application.persistence import retention_deadline
from pycil.assistant.application.run_service import checkpoint_thread_id
from pycil.assistant.infra.models import (
    AssistantAction,
    AssistantActionAudit,
    AssistantRun,
    AssistantRunEvent,
    AssistantThread,
)


async def create_thread(session: AsyncSession, *, owner_id: UUID, title: str) -> AssistantThread:
    thread = AssistantThread(
        owner_id=owner_id, title=title, retention_deadline=retention_deadline()
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


async def list_active_threads(session: AsyncSession, *, owner_id: UUID) -> list[AssistantThread]:
    threads = await session.scalars(
        select(AssistantThread)
        .where(AssistantThread.owner_id == owner_id, AssistantThread.status == "active")
        .order_by(AssistantThread.updated_at.desc())
    )
    return list(threads)


async def delete_thread(session: AsyncSession, thread: AssistantThread, checkpointer) -> None:
    """Delete a thread with its runs, events, and actions; audits survive detached.

    Checkpoint deletion runs first: if it fails, the owner-bound thread is kept
    intact so the client can simply retry.
    """
    if checkpointer is not None:
        await checkpointer.adelete_thread(checkpoint_thread_id(thread.owner_id, thread.id))
    run_ids = select(AssistantRun.id).where(AssistantRun.thread_id == thread.id)
    action_ids = select(AssistantAction.id).where(AssistantAction.run_id.in_(run_ids))
    await session.execute(
        update(AssistantActionAudit)
        .where(AssistantActionAudit.action_id.in_(action_ids))
        .values(action_id=None)
    )
    await session.execute(delete(AssistantAction).where(AssistantAction.run_id.in_(run_ids)))
    await session.execute(delete(AssistantRunEvent).where(AssistantRunEvent.run_id.in_(run_ids)))
    await session.execute(delete(AssistantRun).where(AssistantRun.thread_id == thread.id))
    await session.delete(thread)
    await session.commit()
