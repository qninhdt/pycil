"""Turn-to-run decisions: start, retry, replay, and confirmed resumes.

These behaviors used to live in the send/confirm route bodies; they now pin the
application functions directly, independent of SSE framing.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from pycil.assistant.application import hitl, run_service
from pycil.assistant.application.message_flow import (
    ensure_action_checkpoint_fresh,
    start_message_run,
    stream_resumed_run,
)
from pycil.assistant.application.persistence import run_events
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.infra.models import ActionStatus, AssistantRun, RunStatus
from pycil.common.errors import ConflictError, ServiceUnavailableError

from .conftest import create_run, create_thread, create_user

pytestmark = pytest.mark.asyncio


def _lease_key(owner_id, thread_id) -> str:
    return f"assistant:run:{owner_id}:{thread_id}"


async def _submit(session, thread, owner, message_id=None, content="hello"):
    return await start_message_run(
        session,
        thread_id=thread.id,
        owner_id=owner.id,
        client_message_id=message_id or uuid4(),
        content=content,
    )


async def test_a_new_message_creates_a_pending_run_and_persists_the_user_message(
    session, app_layer_sessions
):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)

    started = await _submit(session, thread, owner)

    assert started.replay_only is False
    assert started.run.status == RunStatus.PENDING
    events = await run_events(session, started.run.id)
    assert [(event.event_type, event.sanitized_payload) for event in events] == [
        ("user_message", {"content": "hello"})
    ]


async def test_a_duplicate_message_replays_instead_of_reexecuting(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    message_id = uuid4()
    run = await create_run(session, thread.id, owner.id, message_id)

    started = await _submit(session, thread, owner, message_id=message_id)

    assert started.replay_only is True
    assert started.run.id == run.id
    assert await run_events(session, run.id) == []


async def test_a_pending_run_with_a_lapsed_lease_is_retried_not_replayed(session):
    """The run never started, so the retry must execute it — without a duplicate
    user_message event, which would corrupt the transcript's turn structure."""
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    message_id = uuid4()
    run = await create_run(session, thread.id, owner.id, message_id)
    run.status = RunStatus.PENDING
    await session.commit()

    started = await _submit(session, thread, owner, message_id=message_id)

    assert started.replay_only is False
    assert started.run.id == run.id
    assert await run_events(session, run.id) == []


async def test_a_pending_run_still_holding_its_lease_replays(session, fake_redis):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    message_id = uuid4()
    run = await create_run(session, thread.id, owner.id, message_id)
    run.status = RunStatus.PENDING
    await session.commit()
    await fake_redis.set(_lease_key(owner.id, thread.id), str(run.id))

    started = await _submit(session, thread, owner, message_id=message_id)

    assert started.replay_only is True


async def test_capacity_rejection_fails_a_created_run_but_leaves_it_reusable(
    session, fake_redis, app_layer_sessions
):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    message_id = uuid4()
    await fake_redis.set(_lease_key(owner.id, thread.id), "someone-else")

    with pytest.raises(ConflictError, match="assistant_capacity_exhausted"):
        await _submit(session, thread, owner, message_id=message_id)

    run = await session.scalar(
        select(AssistantRun).where(AssistantRun.client_message_id == message_id)
    )
    assert run is not None
    assert run.status == RunStatus.FAILED
    assert run.error_code == "capacity_exhausted"


class _Snapshot:
    def __init__(self, checkpoint_id):
        self.config = {"configurable": {"checkpoint_id": checkpoint_id}}


class _CheckpointedGraph:
    def __init__(self, checkpoint_id):
        self._checkpoint_id = checkpoint_id

    async def aget_state(self, config):
        del config
        return _Snapshot(self._checkpoint_id)


async def _pending_action(session, owner, thread, checkpoint_version):
    from pycil.assistant.application.hitl import create_pending_action

    run = await create_run(session, thread.id, owner.id, uuid4())
    return await create_pending_action(
        session,
        run_id=run.id,
        owner_id=owner.id,
        tool="delete_node",
        arguments={},
        checkpoint_version=checkpoint_version,
    )


async def test_an_approval_matching_the_current_checkpoint_passes(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    action = await _pending_action(session, owner, thread, "ckpt-1")

    await ensure_action_checkpoint_fresh(
        session, _CheckpointedGraph("ckpt-1"), owner.id, thread.id, action
    )


async def test_an_approval_on_a_superseded_checkpoint_is_invalidated(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    action = await _pending_action(session, owner, thread, "ckpt-1")

    with pytest.raises(ServiceUnavailableError, match="assistant_action_checkpoint_stale"):
        await ensure_action_checkpoint_fresh(
            session, _CheckpointedGraph("ckpt-2"), owner.id, thread.id, action
        )
    await session.refresh(action)
    assert action.status == ActionStatus.INVALIDATED


async def test_an_action_without_a_usable_checkpoint_skips_the_check(session):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    action = await _pending_action(session, owner, thread, "unknown")

    # A None graph would explode if the check consulted it; passing it proves
    # the unknown-version short-circuit comes first.
    await ensure_action_checkpoint_fresh(session, None, owner.id, thread.id, action)


class _SilentGraph:
    """A graph that completes a run without producing any token or tool update."""

    async def astream(self, *args, **kwargs):
        del args, kwargs
        yield ("updates", {})


@pytest.fixture
def app_layer_sessions(engine, monkeypatch):
    """Point both self-managed session seams at the test database."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(run_service, "async_session_factory", factory)
    monkeypatch.setattr(hitl, "async_session_factory", factory)
    return factory


async def test_an_approved_resume_executes_then_finalizes_the_action(
    engine, session, app_layer_sessions
):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await _pending_action(session, owner, thread, "ckpt-1")
    action.status = ActionStatus.APPROVED
    await session.commit()

    events = [
        event
        async for event in stream_resumed_run(
            _SilentGraph(),
            run,
            AssistantContext(owner.id, owner.token_version, action.id),
            resume="approve",
            action_id=action.id,
        )
    ]

    assert [event.event_type for event in events] == ["done"]
    async with app_layer_sessions() as verify:
        final = await verify.get(type(action), action.id)
    assert final is not None and final.status == ActionStatus.SUCCEEDED


async def test_a_rejected_resume_runs_without_touching_the_action(
    engine, session, app_layer_sessions
):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await _pending_action(session, owner, thread, "ckpt-1")
    action.status = ActionStatus.APPROVED
    await session.commit()

    events = [
        event
        async for event in stream_resumed_run(
            _SilentGraph(),
            run,
            AssistantContext(owner.id, owner.token_version, action.id),
            resume="reject",
            action_id=action.id,
        )
    ]

    assert [event.event_type for event in events] == ["done"]
    async with app_layer_sessions() as verify:
        final = await verify.get(type(action), action.id)
    assert final is not None and final.status == ActionStatus.APPROVED


async def test_an_unconsumed_resume_stream_does_not_execute_the_action(
    engine, session, app_layer_sessions
):
    owner = await create_user(session)
    thread = await create_thread(session, owner.id)
    run = await create_run(session, thread.id, owner.id, uuid4())
    action = await _pending_action(session, owner, thread, "ckpt-1")
    action.status = ActionStatus.APPROVED
    await session.commit()

    generator = stream_resumed_run(
        _SilentGraph(),
        run,
        AssistantContext(owner.id, owner.token_version, action.id),
        resume="approve",
        action_id=action.id,
    )
    await generator.aclose()

    async with app_layer_sessions() as verify:
        final = await verify.get(type(action), action.id)
    assert final is not None and final.status == ActionStatus.APPROVED
