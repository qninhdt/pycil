"""Integration tests for billing period concurrency, idempotent settlement, and plan transitions."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from pycil.account.user import User
from pycil.billing.ledger import (
    get_or_create_usage_period,
    get_usage_allowance,
    record_usage,
    set_plan,
)
from pycil.billing.plans import FeatureKey, PlanKey
from pycil.platform.database import session_scope

pytestmark = pytest.mark.asyncio


async def _user(session, prefix: str = "concurrency") -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_concurrent_period_creation(session):
    user = await _user(session, "concurrent-period")
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

    async def get_or_create():
        async with session_scope() as sess:
            period = await get_or_create_usage_period(sess, user_id=user.id, moment=now)
            await sess.commit()
            return period.id

    tasks = [asyncio.create_task(get_or_create()) for _ in range(10)]
    period_ids = await asyncio.gather(*tasks)

    # Every concurrent task received the exact same period ID
    assert len(set(period_ids)) == 1

    # Exactly one period row was inserted in the database
    count = await session.scalar(
        text("SELECT count(*) FROM usage_periods WHERE user_id = :user_id"),
        {"user_id": user.id},
    )
    assert count == 1


async def test_concurrent_idempotent_settlement(session):
    user = await _user(session, "concurrent-settle")
    period = await get_or_create_usage_period(session, user_id=user.id)
    await session.commit()

    event_key = f"operation:{uuid4()}"
    settle_amount = 250

    async def settle():
        async with session_scope() as sess:
            res = await record_usage(
                sess,
                user_id=user.id,
                period_id=period.id,
                event_key=event_key,
                feature_key=FeatureKey.ASSISTANT,
                units=settle_amount,
            )
            await sess.commit()
            return res

    tasks = [asyncio.create_task(settle()) for _ in range(20)]
    results = await asyncio.gather(*tasks)

    # All 20 returned settlement results for the same event
    assert len(results) == 20
    event_ids = {r.event_id for r in results}
    assert len(event_ids) == 1

    replays = [r.idempotent_replay for r in results]
    # Exactly one executed the initial insert/increment; the other 19 were idempotent replays
    assert replays.count(False) == 1
    assert replays.count(True) == 19

    # Database aggregate used_units incremented exactly once (250, NOT 20 * 250)
    await session.refresh(period)
    assert period.used_units == settle_amount

    # Exactly one usage event row exists
    event_count = await session.scalar(
        text("SELECT count(*) FROM usage_events WHERE event_key = :event_key"),
        {"event_key": event_key},
    )
    assert event_count == 1


async def test_plan_upgrade_increases_current_grant(session):
    user = await _user(session, "upgrade-learner")
    now = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)

    # Start as Free
    period = await get_or_create_usage_period(session, user_id=user.id, moment=now)
    assert period.allowance_units == 1_000_000

    # Use 400,000 units
    await record_usage(
        session,
        user_id=user.id,
        period_id=period.id,
        event_key=f"op:{uuid4()}",
        feature_key=FeatureKey.ASSISTANT,
        units=400_000,
        occurred_at=now,
    )
    await session.commit()

    snapshot_before = await get_usage_allowance(session, user.id, moment=now)
    assert snapshot_before.allowance_units == 1_000_000
    assert snapshot_before.used_units == 400_000
    assert snapshot_before.remaining_units == 600_000

    # Upgrade to Pro
    await set_plan(session, user.id, PlanKey.pro, moment=now)
    await session.commit()

    snapshot_after = await get_usage_allowance(session, user.id, moment=now)
    # Pro grant is 10,000,000 units
    assert snapshot_after.plan == PlanKey.pro
    assert snapshot_after.allowance_units == 10_000_000
    assert snapshot_after.used_units == 400_000
    assert snapshot_after.remaining_units == 9_600_000


async def test_plan_downgrade_does_not_claw_back_current_grant(session):
    user = await _user(session, "downgrade-learner")
    now = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)

    # Provision Pro plan state and period
    await set_plan(session, user.id, PlanKey.pro, moment=now)
    period = await get_or_create_usage_period(session, user_id=user.id, moment=now)
    assert period.allowance_units == 10_000_000

    # Use 2,000,000 units
    await record_usage(
        session,
        user_id=user.id,
        period_id=period.id,
        event_key=f"op:{uuid4()}",
        feature_key=FeatureKey.ASSISTANT,
        units=2_000_000,
        occurred_at=now,
    )
    await session.commit()

    # Downgrade to Free
    await set_plan(session, user.id, PlanKey.free, moment=now)
    await session.commit()

    # In current period: grant is NOT clawed back
    snapshot_current = await get_usage_allowance(session, user.id, moment=now)
    assert snapshot_current.allowance_units == 10_000_000
    assert snapshot_current.used_units == 2_000_000
    assert snapshot_current.remaining_units == 8_000_000

    # Next month: new period is created with Free plan allowance (1,000,000)
    next_month = now + timedelta(days=32)
    snapshot_next = await get_usage_allowance(session, user.id, moment=next_month)
    assert snapshot_next.plan == PlanKey.free
    assert snapshot_next.allowance_units == 1_000_000
    assert snapshot_next.used_units == 0
    assert snapshot_next.remaining_units == 1_000_000
