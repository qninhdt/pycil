"""Stripe billing scaffolding: checkout session + webhook handler.

Stub-only per plan.md Hard Decisions: ships subscriptions table + webhook
route + plan-gate decorator. NO checkout UI in v0.2; all users 'free' tier.
ENFORCE_TIERS feature flag default false.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_log = logging.getLogger(__name__)


async def get_or_create_stripe_customer(
    session: AsyncSession,
    *,
    user_id: UUID,
    email: str,
) -> str:
    """Fetch users.stripe_customer_id or create via Stripe + persist."""
    row = (
        await session.execute(
            text("SELECT stripe_customer_id FROM users WHERE id = :uid"),
            {"uid": user_id},
        )
    ).first()
    if row and row.stripe_customer_id:
        return row.stripe_customer_id

    import asyncio

    import stripe

    customer = await asyncio.to_thread(
        stripe.Customer.create, email=email, metadata={"user_id": str(user_id)}
    )
    await session.execute(
        text(
            "UPDATE users SET stripe_customer_id = :cid WHERE id = :uid"
        ),
        {"cid": customer.id, "uid": user_id},
    )
    await session.commit()
    return customer.id


async def upsert_subscription(
    session: AsyncSession,
    *,
    user_id: UUID,
    tier: str,
    stripe_subscription_id: str | None,
    current_period_end_epoch: int | None,
    status_str: str,
    event_created_epoch: int,
    event_id: str,
) -> bool:
    """Apply Stripe subscription state with out-of-order protection.

    Returns True if the row was inserted/updated, False when an older event
    (by `(event_created, event_id)` tiebreak) was rejected. Caller logs.
    """
    row = (
        await session.execute(
            text(
                """
                INSERT INTO subscriptions (user_id, tier, stripe_subscription_id,
                                           current_period_end, status,
                                           last_event_at, last_event_id)
                VALUES (:uid, :tier, :sid,
                        CASE WHEN :pe IS NULL THEN NULL ELSE to_timestamp(:pe) END,
                        :status, to_timestamp(:ev_ts), :ev_id)
                ON CONFLICT (user_id) DO UPDATE
                  SET tier = EXCLUDED.tier,
                      stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                      current_period_end = EXCLUDED.current_period_end,
                      status = EXCLUDED.status,
                      last_event_at = EXCLUDED.last_event_at,
                      last_event_id = EXCLUDED.last_event_id,
                      updated_at = NOW()
                  WHERE (EXCLUDED.last_event_at, EXCLUDED.last_event_id)
                      > (subscriptions.last_event_at, subscriptions.last_event_id)
                RETURNING user_id
                """
            ),
            {
                "uid": user_id,
                "tier": tier,
                "sid": stripe_subscription_id,
                "pe": current_period_end_epoch,
                "status": status_str,
                "ev_ts": event_created_epoch,
                "ev_id": event_id,
            },
        )
    ).first()
    await session.commit()
    if row is None:
        _log.warning(
            "stripe_webhook_out_of_order",
            extra={
                "event_id": event_id,
                "event_created": event_created_epoch,
                "user_id": str(user_id),
            },
        )
        return False
    return True


async def insert_webhook_event_or_dup(
    session: AsyncSession, *, event_id: str
) -> bool:
    """Insert event_id; returns True if inserted, False ONLY if PK conflict.

    Other DB errors propagate so Stripe retries (vs being marked as
    silent duplicates and lost forever).
    """
    from sqlalchemy.exc import IntegrityError

    try:
        await session.execute(
            text(
                "INSERT INTO stripe_webhook_events (event_id) VALUES (:eid)"
            ),
            {"eid": event_id},
        )
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False


async def get_user_tier(
    session: AsyncSession, *, user_id: UUID
) -> str:
    row = (
        await session.execute(
            text("SELECT tier FROM subscriptions WHERE user_id = :uid"),
            {"uid": user_id},
        )
    ).first()
    return row.tier if row else "free"
