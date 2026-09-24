"""Durable Thread/Run lifecycle without action or event persistence."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.assistant.application import thread_lifecycle
from pycil.assistant.application.persistence import retention_deadline
from pycil.assistant.infra.models import AssistantThread

from .conftest import create_thread, create_user

pytestmark = pytest.mark.asyncio


async def test_create_thread_stamps_a_future_retention_deadline(session):
    owner = await create_user(session)
    thread = await thread_lifecycle.create_thread(session, owner_id=owner.id, title="Fresh")

    assert thread.retention_deadline > datetime.now(UTC)


async def test_listing_returns_only_the_owners_active_threads(session):
    owner = await create_user(session)
    intruder = await create_user(session, "thread-list-intruder@example.test")
    active = await create_thread(session, owner.id, title="Assistant test")
    archived = AssistantThread(
        owner_id=owner.id,
        title="Archived",
        retention_deadline=retention_deadline(),
        status="archived",
    )
    session.add(archived)
    await session.commit()
    theirs = await create_thread(session, intruder.id, title="Theirs")

    rows = await thread_lifecycle.list_active_threads(session, owner_id=owner.id)

    assert [row.id for row in rows] == [active.id]
    assert all(row.id != theirs.id for row in rows)


async def test_deleting_a_thread_removes_its_checkpoint_and_row(engine, session):
    """The checkpointer is the conversation store, so deleting a thread must clear both.

    A thread row left without its checkpoint would keep an unreachable conversation;
    a checkpoint left without its row would keep conversation content past the
    retention the row exists to enforce.
    """
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)

    class Checkpointer:
        def __init__(self):
            self.deleted: list[str] = []

        async def adelete_thread(self, checkpoint_thread: str) -> None:
            self.deleted.append(checkpoint_thread)

    checkpointer = Checkpointer()
    await thread_lifecycle.delete_thread(session, thread, checkpointer)

    assert checkpointer.deleted == [f"assistant:{owner.id}:{thread.id}"]
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as verify:
        assert await verify.get(AssistantThread, thread.id) is None


async def test_failed_checkpoint_cleanup_keeps_the_thread_for_retry(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)

    class FailingCheckpointer:
        async def adelete_thread(self, checkpoint_thread: str) -> None:
            del checkpoint_thread
            raise RuntimeError("checkpoint store unavailable")

    with pytest.raises(RuntimeError, match="checkpoint store unavailable"):
        await thread_lifecycle.delete_thread(session, thread, FailingCheckpointer())

    assert await session.get(AssistantThread, thread.id) is not None
