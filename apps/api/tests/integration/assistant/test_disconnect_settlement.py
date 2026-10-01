"""A disconnected turn charges completed calls and releases its execution slot.

The accepted behavior is that a client disconnect before graph exit may lose the
in-flight model call. Completed calls are charged and the turn lease is freed.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ag_ui.core import RunStartedEvent
from sqlalchemy import select

from pycil.account.user import User
from pycil.assistant.agent.context import AssistantContext
from pycil.assistant.turns import stream as router
from pycil.assistant.turns.leases import acquire_turn_lease, thread_lease_key
from pycil.assistant.turns.usage import CallUsage
from pycil.billing.ledger import require_usage_allowed
from pycil.billing.models import UsageEvent, UsagePeriod
from pycil.billing.plans import FeatureKey, PlanKey

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


async def _drain(agent, context, user_id, period_id, occurred_at, redis):
    frames = []
    thread_id = uuid4()
    lease = await acquire_turn_lease(redis, user_id, thread_id, PlanKey.free)
    assert lease is not None
    with pytest.raises(asyncio.CancelledError):
        async for frame in router._events(
            agent,
            SimpleNamespace(thread_id=str(thread_id), run_id="run-disconnect"),
            context,
            user_id,
            period_id,
            occurred_at,
            f"assistant:{user_id}:{uuid4().hex}",
            redis,
            _Graph(),
            lease,
            interrupt_id=None,
            free_rejection=False,
        ):
            frames.append(frame)
    return frames, thread_id


async def test_a_disconnected_turn_charges_completed_calls_and_frees_the_lease(session, fake_redis):
    user = User(email="disconnect@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    context = AssistantContext(user_id=user.id, model_id="gemini-3.8-flash")
    context.usage.add("gemini-3.8-flash", CallUsage(input_tokens=1_000, output_tokens=100))

    now = datetime.now(UTC)
    balance = await require_usage_allowed(
        session, user.id, feature=FeatureKey.ASSISTANT, moment=now
    )
    await session.commit()

    frames, thread_id = await _drain(
        _Agent(raise_after_first=True),
        context,
        user.id,
        balance.period_id,
        now,
        fake_redis,
    )

    assert len(frames) == 1
    events = list(
        (
            await session.scalars(
                select(UsageEvent)
                .join(UsagePeriod, UsagePeriod.id == UsageEvent.period_id)
                .where(
                    UsagePeriod.user_id == user.id,
                )
            )
        ).all()
    )
    assert len(events) == 1
    assert events[0].details["status"] == "disconnected"
    assert not await fake_redis.exists(thread_lease_key(thread_id))
