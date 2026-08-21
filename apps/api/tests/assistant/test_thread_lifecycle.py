"""Thread creation, listing, and the deletion cascade, at the application layer."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.assistant.application import run_service
from pycil.assistant.application.hitl import create_pending_action
from pycil.assistant.application.persistence import retention_deadline
from pycil.assistant.application.thread_lifecycle import (
    create_thread,
    delete_thread,
    list_active_threads,
)
from pycil.assistant.infra.models import (
    AssistantActionAudit,
    AssistantRunEvent,
    AssistantThread,
)

from .conftest import create_run, create_user

pytestmark = pytest.mark.asyncio


async def test_create_thread_stamps_a_future_retention_deadline(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner_id=owner.id, title="Fresh")

    assert thread.retention_deadline > datetime.now(UTC)


async def test_listing_returns_only_the_owners_active_threads(session):
    owner = await create_user(session)
    intruder = await create_user(session, "thread-list-intruder@example.test")
    active = await create_thread(session, owner_id=owner.id, title="Assistant test")
    archived = AssistantThread(
        owner_id=owner.id,
        title="Archived",
        retention_deadline=retention_deadline(),
        status="archived",
    )
    session.add(archived)
    await session.commit()
    theirs = await create_thread(session, owner_id=intruder.id, title="Theirs")

    rows = await list_active_threads(session, owner_id=owner.id)

    assert [row.id for row in rows] == [active.id]
    assert all(row.id != theirs.id for row in rows)


async def test_deleting_a_thread_removes_runs_events_actions_and_detaches_audits(
    engine, session, monkeypatch
):
    owner = await create_user(session)
    thread = await create_thread(session, owner_id=owner.id, title="Assistant test")
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="delete_node",
        arguments={},
        checkpoint_version=f"run:{run.id}",
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(run_service, "async_session_factory", factory)
    await run_service.append_event(run.id, "token", {"content": "one"})

    class Checkpointer:
        def __init__(self):
            self.deleted: list[str] = []

        async def adelete_thread(self, checkpoint_thread: str) -> None:
            self.deleted.append(checkpoint_thread)

    checkpointer = Checkpointer()
    await delete_thread(session, thread, checkpointer)

    assert checkpointer.deleted == [f"assistant:{owner.id}:{thread.id}"]
    async with factory() as verify:
        assert await verify.get(type(thread), thread.id) is None
        assert await verify.get(type(run), run.id) is None
        assert await verify.get(type(action), action.id) is None
        remaining_events = list(
            await verify.scalars(
                select(AssistantRunEvent).where(AssistantRunEvent.run_id == run.id)
            )
        )
        audits = list(
            await verify.scalars(
                select(AssistantActionAudit).where(
                    AssistantActionAudit.correlation_id == action.correlation_id
                )
            )
        )
    assert remaining_events == []
    assert audits
    assert all(entry.action_id is None for entry in audits)


async def test_a_failed_checkpoint_deletion_keeps_the_thread_for_retry(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner_id=owner.id, title="Assistant test")

    class FailingCheckpointer:
        async def adelete_thread(self, checkpoint_thread: str) -> None:
            del checkpoint_thread
            raise RuntimeError("checkpoint store unavailable")

    with pytest.raises(RuntimeError, match="checkpoint store unavailable"):
        await delete_thread(session, thread, FailingCheckpointer())

    assert await session.get(type(thread), thread.id) is not None
