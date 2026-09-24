"""Assistant thread creation, listing, and deletion."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.application.ag_ui_agent import checkpoint_thread_id
from pycil.assistant.application.persistence import retention_deadline
from pycil.assistant.infra.models import AssistantThread


async def create_thread(session: AsyncSession, *, owner_id: UUID, title: str) -> AssistantThread:
    thread = AssistantThread(
        owner_id=owner_id, title=title, retention_deadline=retention_deadline()
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


async def list_active_threads(session: AsyncSession, *, owner_id: UUID) -> list[AssistantThread]:
    rows = await session.scalars(
        select(AssistantThread)
        .where(AssistantThread.owner_id == owner_id, AssistantThread.status == "active")
        .order_by(AssistantThread.updated_at.desc())
    )
    return list(rows)


async def delete_thread(session: AsyncSession, thread: AssistantThread, checkpointer) -> None:
    if checkpointer is not None:
        await checkpointer.adelete_thread(checkpoint_thread_id(thread.owner_id, thread.id))
    await session.delete(thread)
    await session.commit()
