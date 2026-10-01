"""An AG-UI run settles per execution segment with idempotent replay and admission gating."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ag_ui.core import ResumeEntry, RunAgentInput, RunFinishedEvent
from sqlalchemy import select

from pycil.account.schemas import CurrentUser
from pycil.account.user import User
from pycil.assistant.models import AssistantThread
from pycil.assistant.turns import stream as router
from pycil.assistant.turns.settlement import settle_assistant_segment
from pycil.assistant.turns.usage import CallUsage, TurnUsage, usage_units_for
from pycil.billing.errors import UsageQuotaExhaustedError
from pycil.billing.ledger import (
    get_or_create_usage_period,
    require_usage_allowed,
)
from pycil.billing.models import UsageEvent, UsagePeriod
from pycil.billing.plans import FeatureKey

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_interrupted_run_and_resume_settle_as_independent_segments(session, fake_redis):
    user = await _user(session, "assistant-resume@example.test")
    thread_id = uuid4()
    run_id = "run-stable-across-approval"
    interrupt_id = "interrupt-approval-1"
    initial_key = f"assistant:{user.id}:{uuid4().hex}"
    resume_key = f"assistant:{user.id}:{uuid4().hex}"

    # Segment 1: Initial execution up to interrupt
    now_1 = datetime.now(UTC)
    balance_1 = await require_usage_allowed(
        session, user.id, feature=FeatureKey.ASSISTANT, moment=now_1
    )
    usage_1 = TurnUsage()
    usage_1.add("gemini-3.8-flash", CallUsage(input_tokens=1_000_000, output_tokens=100))

    settlement_1 = await settle_assistant_segment(
        session,
        user_id=user.id,
        period_id=balance_1.period_id,
        occurred_at=now_1,
        event_key=initial_key,
        run_id=run_id,
        status="interrupted",
        usage=usage_1,
        thread_id=str(thread_id),
        model_id="gemini-3.8-flash",
    )
    assert settlement_1 is not None
    assert settlement_1.event_key == initial_key
    assert settlement_1.units == usage_units_for(usage_1)
    await session.commit()

    # Retry of Segment 1 is idempotent
    retry_1 = await settle_assistant_segment(
        session,
        user_id=user.id,
        period_id=balance_1.period_id,
        occurred_at=now_1,
        event_key=initial_key,
        run_id=run_id,
        status="interrupted",
        usage=usage_1,
        thread_id=str(thread_id),
        model_id="gemini-3.8-flash",
    )
    assert retry_1 is not None
    assert retry_1.idempotent_replay is True
    assert retry_1.event_id == settlement_1.event_id

    # Segment 2: Resume after HITL approval
    now_2 = datetime.now(UTC)
    balance_2 = await require_usage_allowed(
        session, user.id, feature=FeatureKey.ASSISTANT, moment=now_2
    )
    usage_2 = TurnUsage()
    usage_2.add("gemini-3.8-flash", CallUsage(input_tokens=250_000, output_tokens=25))

    settlement_2 = await settle_assistant_segment(
        session,
        user_id=user.id,
        period_id=balance_2.period_id,
        occurred_at=now_2,
        event_key=resume_key,
        run_id=run_id,
        status="completed",
        usage=usage_2,
        interrupt_id=interrupt_id,
        thread_id=str(thread_id),
        model_id="gemini-3.8-flash",
    )
    assert settlement_2 is not None
    assert settlement_2.event_key == resume_key
    assert settlement_2.units == usage_units_for(usage_2)
    await session.commit()

    # Verify both segment events exist independently in UsageEvent
    events = list(
        (
            await session.scalars(
                select(UsageEvent)
                .join(UsagePeriod, UsagePeriod.id == UsageEvent.period_id)
                .where(UsagePeriod.user_id == user.id)
                .order_by(UsageEvent.created_at.asc())
            )
        ).all()
    )
    assert len(events) == 2
    assert events[0].event_key == initial_key
    assert events[0].details["status"] == "interrupted"
    assert events[0].details["segment"] == "initial"
    assert events[1].event_key == resume_key
    assert events[1].details["status"] == "completed"
    assert events[1].details["segment"] == "resume"
    assert events[1].details["interrupt_id"] == interrupt_id


async def test_assistant_admission_requires_positive_credit(session, fake_redis):
    user = await _user(session, "no-credit@example.test")
    thread = AssistantThread(
        owner_id=user.id,
        title="No credit",
        retention_deadline=datetime.now(UTC) + timedelta(days=30),
    )
    session.add(thread)
    await session.commit()
    period = await get_or_create_usage_period(session, user_id=user.id)
    period.used_units = period.allowance_units
    await session.commit()

    dummy_graph = SimpleNamespace(
        aget_state=lambda config: SimpleNamespace(values={}, interrupts=())
    )

    # async function for aget_state
    async def _async_get_state(config):
        return SimpleNamespace(values={}, interrupts=())

    dummy_graph.aget_state = _async_get_state

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(assistant_graph=dummy_graph, assistant_agent=object())
        )
    )
    body = RunAgentInput(
        thread_id=str(thread.id),
        run_id=str(uuid4()),
        messages=[],
        tools=[],
        context=[],
        forwarded_props={},
    )

    with pytest.raises(UsageQuotaExhaustedError):
        await router.run_turn(
            body,
            request,
            user=CurrentUser(id=user.id, email=user.email),
            session=session,
            redis=fake_redis,
        )

    assert not await fake_redis.keys("assistant:slot:*")
    assert not await fake_redis.keys("assistant:running:*")


async def test_reject_can_close_a_pending_approval_with_zero_credit(session, fake_redis):
    user = await _user(session, "zero-credit-reject@example.test")
    thread = AssistantThread(
        owner_id=user.id,
        title="Pending approval",
        retention_deadline=datetime.now(UTC) + timedelta(days=30),
    )
    session.add(thread)
    await session.commit()
    period = await get_or_create_usage_period(session, user_id=user.id)
    period.used_units = period.allowance_units
    await session.commit()

    class Graph:
        async def aget_state(self, _config):
            return SimpleNamespace(
                values={"selected_model_id": "gemini-3.8-flash", "selected_effort": "none"},
                interrupts=({"action_requests": [{"name": "delete_node"}]},),
            )

    class Agent:
        def clone(self):
            return self

        async def run(self, body):
            yield RunFinishedEvent(thread_id=body.thread_id, run_id=body.run_id)

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(assistant_graph=Graph(), assistant_agent=Agent()))
    )
    body = RunAgentInput(
        thread_id=str(thread.id),
        run_id=str(uuid4()),
        messages=[],
        tools=[],
        context=[],
        forwarded_props={},
        resume=[
            ResumeEntry(
                interrupt_id="interrupt-1", status="resolved", payload={"decisions": ["reject"]}
            )
        ],
    )
    response = await router.run_turn(
        body,
        request,
        user=CurrentUser(id=user.id, email=user.email),
        session=session,
        redis=fake_redis,
    )
    frames = [frame async for frame in response.body_iterator]

    last_frame = frames[-1] if isinstance(frames[-1], bytes) else frames[-1].encode()
    assert b"RUN_FINISHED" in last_frame
    events = list(
        (
            await session.scalars(
                select(UsageEvent)
                .join(UsagePeriod, UsagePeriod.id == UsageEvent.period_id)
                .where(UsagePeriod.user_id == user.id)
            )
        ).all()
    )
    assert events == []
    assert not await fake_redis.keys("assistant:slot:*")
    assert not await fake_redis.keys("assistant:running:*")
