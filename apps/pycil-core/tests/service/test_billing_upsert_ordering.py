"""`billing_service.upsert_subscription` out-of-order ordering matrix.

Pinned via the WHERE-clause composite tiebreak `(last_event_at, last_event_id)`:
- Newer event wins (UPDATE applied).
- Older event rejected (returns False, row unchanged).
- Same ts, lex-smaller event_id rejected.
- Same ts, lex-larger event_id wins.
- Exact replay rejected (strict `>` comparator).
- Tier downgrade race: deletion lands first, stale "still-pro" arrives → user stays free.
- Unicode event_id roundtrips.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from pycil_core.services import billing_service


async def _row(session, user_id):
    return (
        await session.execute(
            text(
                "SELECT tier, last_event_at, last_event_id "
                "FROM subscriptions WHERE user_id = :u"
            ),
            {"u": user_id},
        )
    ).first()


async def test_first_event_inserts_new_row(session, test_user) -> None:
    ok = await billing_service.upsert_subscription(
        session,
        user_id=test_user["id"],
        tier="pro",
        stripe_subscription_id="sub_001",
        current_period_end_epoch=2000,
        status_str="active",
        event_created_epoch=100,
        event_id="evt_001",
    )
    assert ok is True
    row = await _row(session, test_user["id"])
    assert row is not None
    assert row.tier == "pro"
    assert row.last_event_id == "evt_001"


async def test_newer_event_wins(session, test_user) -> None:
    await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_001", current_period_end_epoch=2000,
        status_str="active", event_created_epoch=100, event_id="evt_001",
    )
    ok = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_001", current_period_end_epoch=3000,
        status_str="active", event_created_epoch=200, event_id="evt_002",
    )
    assert ok is True
    row = await _row(session, test_user["id"])
    assert row.last_event_id == "evt_002"


async def test_older_event_rejected(session, test_user) -> None:
    await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_001", current_period_end_epoch=2000,
        status_str="active", event_created_epoch=200, event_id="evt_002",
    )
    ok = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="free",
        stripe_subscription_id=None, current_period_end_epoch=None,
        status_str="canceled", event_created_epoch=150, event_id="evt_old",
    )
    assert ok is False
    row = await _row(session, test_user["id"])
    # Still pro because the older event was rejected.
    assert row.tier == "pro"
    assert row.last_event_id == "evt_002"


async def test_same_ts_lex_tiebreak(session, test_user) -> None:
    await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_001", current_period_end_epoch=2000,
        status_str="active", event_created_epoch=200, event_id="evt_005",
    )
    # Same ts, lex-smaller id → rejected.
    ok_smaller = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_x", current_period_end_epoch=2000,
        status_str="active", event_created_epoch=200, event_id="evt_001",
    )
    assert ok_smaller is False

    # Same ts, lex-larger id → wins.
    ok_larger = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_y", current_period_end_epoch=2000,
        status_str="active", event_created_epoch=200, event_id="evt_009",
    )
    assert ok_larger is True
    row = await _row(session, test_user["id"])
    assert row.last_event_id == "evt_009"


async def test_exact_replay_rejected(session, test_user) -> None:
    """Strict `>`: identical (ts, id) replay returns False."""
    ok_first = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_001", current_period_end_epoch=2000,
        status_str="active", event_created_epoch=200, event_id="evt_replay",
    )
    ok_replay = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_001", current_period_end_epoch=2000,
        status_str="active", event_created_epoch=200, event_id="evt_replay",
    )
    assert ok_first is True
    assert ok_replay is False


async def test_downgrade_race_keeps_free(session, test_user) -> None:
    """Deletion lands first (newer), stale `still-pro` arrives later (older)
    → user stays free."""
    # Newest event: deletion → free.
    await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="free",
        stripe_subscription_id=None, current_period_end_epoch=None,
        status_str="canceled", event_created_epoch=300, event_id="evt_del",
    )
    # Older "still pro" arrives.
    ok = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_001", current_period_end_epoch=4000,
        status_str="active", event_created_epoch=250, event_id="evt_pro",
    )
    assert ok is False
    row = await _row(session, test_user["id"])
    assert row.tier == "free"


async def test_null_period_end_preserved(session, test_user) -> None:
    ok = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="free",
        stripe_subscription_id=None, current_period_end_epoch=None,
        status_str="canceled", event_created_epoch=100, event_id="evt_x",
    )
    assert ok is True
    row = (
        await session.execute(
            text(
                "SELECT current_period_end FROM subscriptions WHERE user_id = :u"
            ),
            {"u": test_user["id"]},
        )
    ).first()
    assert row.current_period_end is None


async def test_unicode_event_id_roundtrips(session, test_user) -> None:
    eid = "evt_🎉_001"
    ok = await billing_service.upsert_subscription(
        session, user_id=test_user["id"], tier="pro",
        stripe_subscription_id="sub_001", current_period_end_epoch=2000,
        status_str="active", event_created_epoch=100, event_id=eid,
    )
    assert ok is True
    row = await _row(session, test_user["id"])
    assert row.last_event_id == eid


async def test_get_user_tier_default_free(session, test_user) -> None:
    tier = await billing_service.get_user_tier(session, user_id=test_user["id"])
    assert tier == "free"
