"""Assistant thread creation, listing, and deletion."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.agent.adapter import checkpoint_thread_id
from pycil.assistant.models import AssistantThread
from pycil.assistant.schemas import ThreadStateRead
from pycil.assistant.thread_access import retention_deadline


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


def _message_dict(message) -> dict:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump(mode="json", exclude_none=True)
    return {"content": str(message)}


async def read_state(graph, owner_id: UUID, thread_id: UUID) -> ThreadStateRead:
    """Read the durable conversation from the LangGraph checkpoint."""
    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": checkpoint_thread_id(owner_id, thread_id)}}
    )
    values = getattr(snapshot, "values", {}) or {}
    messages = [_message_dict(message) for message in values.get("messages", [])]
    interrupts = []
    for interrupt in getattr(snapshot, "interrupts", ()) or ():
        value = getattr(interrupt, "value", interrupt)
        payload = value.copy() if isinstance(value, dict) else {"value": str(value)}
        interrupt_id = getattr(interrupt, "id", None)
        if interrupt_id is not None:
            payload["id"] = str(interrupt_id)
        interrupts.append(payload)
    return ThreadStateRead(messages=messages, interrupts=interrupts)


async def delete_thread(session: AsyncSession, thread: AssistantThread, checkpointer) -> None:
    if checkpointer is not None:
        await checkpointer.adelete_thread(checkpoint_thread_id(thread.owner_id, thread.id))
    await session.delete(thread)
    await session.commit()
