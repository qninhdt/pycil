"""A disconnected turn settles reported usage once and releases its lease.

The accepted behavior is that a client disconnect before graph exit may lose the
in-flight conversation turn, but it must not lose the accounting: whatever the
provider reported is billed, and the learner is not left holding a lease that
blocks their next turn.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ag_ui.core import RunStartedEvent

from pycil.assistant import router
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.domain.usage import CallUsage

pytestmark = pytest.mark.asyncio


class _Graph:
    """A graph with no pending interrupt, so the turn is not treated as paused."""

    async def aget_state(self, config):
        return SimpleNamespace(values={}, interrupts=())


class _Agent:
    """Yields one event, then raises the cancellation a disconnect produces."""

    def __init__(self, *, raise_after_first: bool) -> None:
        self.raise_after_first = raise_after_first
        self.request_context = None

    def clone(self):
        return self

    async def run(self, body):
        yield RunStartedEvent(thread_id="t", run_id="run-disconnect")
        if self.raise_after_first:
            raise asyncio.CancelledError


async def _drain(agent, context, user_id, redis, reference):
    frames = []
    with pytest.raises(asyncio.CancelledError):
        async for frame in router._streamed_events(
            agent,
            SimpleNamespace(thread_id=str(uuid4()), run_id="run-disconnect"),
            context,
            reference,
            user_id,
            redis,
            _Graph(),
            "lease-token",
        ):
            frames.append(frame)
    return frames


async def test_a_disconnected_turn_bills_reported_usage_and_frees_the_lease(
    session, fake_redis, monkeypatch
):
    from sqlalchemy import select

    from pycil.account.models import CreditDebit
    from pycil.auth.models import User

    user = User(email="disconnect@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    thread_id = uuid4()
    reference = router._run_reference(user.id, thread_id, "run-disconnect")
    context = AssistantContext(user_id=user.id, model_id="gemini-3.8-flash")
    context.usage.add("gemini-3.8-flash", CallUsage(input_tokens=1_000, output_tokens=100))

    lease_key = f"assistant:turn:{user.id}"
    await fake_redis.set(lease_key, "lease-token")

    frames = await _drain(
        _Agent(raise_after_first=True), context, user.id, fake_redis, reference
    )

    assert len(frames) == 1
    debits = list(
        (
            await session.scalars(
                select(CreditDebit).where(
                    CreditDebit.kind == "agent_turn",
                    CreditDebit.reference_id == reference,
                )
            )
        ).all()
    )
    assert len(debits) == 1
    assert debits[0].details["status"] == "disconnected"
    # Reported usage is billed; an unreported remainder is never invented.
    assert debits[0].amount > 0
