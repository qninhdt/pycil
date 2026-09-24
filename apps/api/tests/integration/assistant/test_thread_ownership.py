"""Thread ownership is checked before the adapter reads a checkpoint.

The AG-UI endpoint takes the checkpoint key straight from the request body, so a
client-supplied thread id is a *request* to read a conversation rather than an
authorization to read it. These tests assert the refusal happens first, before any
graph or checkpointer access.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ag_ui.core import RunAgentInput

from pycil.assistant import router
from pycil.assistant.infra.models import AssistantThread
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import NotFoundError

pytestmark = pytest.mark.asyncio


class RecordingGraph:
    """A graph stub that records whether it was reached at all."""

    def __init__(self):
        self.calls: list[str] = []

    async def aget_state(self, config):
        self.calls.append("aget_state")
        return SimpleNamespace(values={}, interrupts=())


async def _owner_with_thread(session, email: str) -> tuple[User, AssistantThread]:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    thread = AssistantThread(
        owner_id=user.id,
        title="Owned",
        retention_deadline=datetime.now(UTC) + timedelta(days=30),
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return user, thread


def _request(graph) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(assistant_graph=graph, assistant_agent=object())
        )
    )


def _body(thread_id) -> RunAgentInput:
    return RunAgentInput(
        thread_id=str(thread_id),
        run_id=str(uuid4()),
        messages=[],
        tools=[],
        context=[],
        forwarded_props={},
    )


async def test_another_learners_thread_is_refused_before_any_checkpoint_read(
    session, fake_redis
):
    """A foreign thread answers exactly like a missing one, and reads nothing."""
    _, thread = await _owner_with_thread(session, "owner-idor@example.test")
    intruder = User(email="intruder-idor@example.test")
    session.add(intruder)
    await session.commit()
    await session.refresh(intruder)

    graph = RecordingGraph()
    with pytest.raises(NotFoundError):
        await router.ag_ui_run(
            _body(thread.id),
            _request(graph),
            user=CurrentUser(id=intruder.id, email=intruder.email),
            session=session,
            redis=fake_redis,
        )

    assert graph.calls == []
    assert not await fake_redis.keys("assistant:turn:*")


async def test_a_missing_thread_is_refused_identically(session, fake_redis):
    """The refusal must not reveal which thread ids exist."""
    user = User(email="missing-thread@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    graph = RecordingGraph()
    with pytest.raises(NotFoundError):
        await router.ag_ui_run(
            _body(uuid4()),
            _request(graph),
            user=CurrentUser(id=user.id, email=user.email),
            session=session,
            redis=fake_redis,
        )

    assert graph.calls == []
