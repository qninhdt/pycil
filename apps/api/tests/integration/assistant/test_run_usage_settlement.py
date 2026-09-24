"""An AG-UI resume extends the same cumulative, explainable ledger debit."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ag_ui.core import RunAgentInput
from sqlalchemy import select

from pycil.account import credit
from pycil.account.models import CreditDebit
from pycil.account.plans import AccountPlan, period_grant
from pycil.assistant import router
from pycil.assistant.domain.context import AssistantContext
from pycil.assistant.domain.usage import CallUsage, TurnUsage, milli_credits_for
from pycil.assistant.infra.models import AssistantThread
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_interrupted_usage_retries_and_resumes_as_one_debit(
    session, fake_redis, monkeypatch
):
    user = await _user(session, "assistant-resume@example.test")
    thread_id = uuid4()
    run_id = "run-stable-across-approval"
    reference = router._run_reference(user.id, thread_id, run_id)
    context = AssistantContext(user_id=user.id, model_id="gemini-3.8-flash")
    context.usage.add(
        "gemini-3.8-flash", CallUsage(input_tokens=1_000_000, output_tokens=100)
    )

    persist = router._persist_usage

    async def fail_once(*args, **kwargs):
        raise RuntimeError("database temporarily unavailable")

    monkeypatch.setattr(router, "_persist_usage", fail_once)
    await router._settle(
        reference,
        user.id,
        context,
        run_id=run_id,
        thread_id=str(thread_id),
        status="interrupted",
        redis=fake_redis,
        lease_token="lease-token",
    )
    pending_key = router._pending_usage_key(reference)
    assert await fake_redis.exists(pending_key)

    monkeypatch.setattr(router, "_persist_usage", persist)
    saved = await router._load_agent_turn(session, fake_redis, user.id, reference)
    assert saved is not None and saved.details["status"] == "interrupted"
    assert not await fake_redis.exists(pending_key)

    resumed_usage = TurnUsage.from_dict(saved.details["usage"])
    resumed_usage.add("gemini-3.8-flash", CallUsage(input_tokens=250_000, output_tokens=25))
    resumed_context = AssistantContext(
        user_id=user.id,
        model_id="gemini-3.8-flash",
        usage=resumed_usage,
    )
    await router._settle(
        reference,
        user.id,
        resumed_context,
        run_id=run_id,
        thread_id=str(thread_id),
        status="completed",
        redis=fake_redis,
        lease_token="lease-token",
    )

    debits = list(
        (
            await session.scalars(
                select(CreditDebit).where(
                    CreditDebit.kind == credit.CREDIT_KIND_AGENT_TURN,
                    CreditDebit.reference_id == reference,
                )
            )
        ).all()
    )
    assert len(debits) == 1
    await session.refresh(debits[0])
    assert debits[0].amount == milli_credits_for(resumed_usage)
    assert debits[0].details["status"] == "completed"
    assert debits[0].details["usage"] == resumed_usage.to_dict()
    assert (
        debits[0].details["usage"]["calls"][0]["rates"]["input_usd_per_m"]
        == "0.3"
    )


async def test_assistant_admission_requires_positive_credit(session, fake_redis):
    user = await _user(session, "no-credit@example.test")
    thread = AssistantThread(
        owner_id=user.id,
        title="No credit",
        retention_deadline=datetime.now(UTC) + timedelta(days=30),
    )
    session.add(thread)
    await session.commit()
    row = await credit._ensure_credit(session, user.id)
    row.plan = AccountPlan.free
    row.period_used = period_grant(AccountPlan.free)
    row.topup_balance = 0
    await session.commit()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(assistant_graph=object(), assistant_agent=object())
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

    with pytest.raises(credit.CreditExhaustedError):
        await router.ag_ui_run(
            body,
            request,
            user=CurrentUser(id=user.id, email=user.email),
            session=session,
            redis=fake_redis,
        )

    assert not await fake_redis.keys("assistant:turn:*")
