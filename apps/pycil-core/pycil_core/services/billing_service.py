"""Stripe billing scaffolding: checkout session + webhook handler.

Stub-only per plan.md Hard Decisions: ships subscriptions table + webhook
route + plan-gate decorator. NO checkout UI in v0.2; all users 'free' tier.
ENFORCE_TIERS feature flag default false.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from shared.db import Subscription, User
from sqlalchemy import tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

_log = logging.getLogger(__name__)


async def get_or_create_stripe_customer(
    session: AsyncSession,
    *,
    user_id: UUID,
    email: str,
) -> str:
    """Fetch users.stripe_customer_id or create via Stripe + persist."""
    customer_id = (
        await session.exec(select(User.stripe_customer_id).where(User.id == user_id))
    ).first()
    if customer_id:
        return customer_id

    import asyncio

    import stripe

    customer = await asyncio.to_thread(
        stripe.Customer.create, email=email, metadata={"user_id": str(user_id)}
    )
    await session.exec(
        update(User)
        .where(User.id == user_id)
        .values(stripe_customer_id=customer.id)
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
    current_period_end = (
        datetime.fromtimestamp(current_period_end_epoch, UTC)
        if current_period_end_epoch is not None
        else None
    )
    event_created_at = datetime.fromtimestamp(event_created_epoch, UTC)
    stmt = insert(Subscription).values(
        user_id=user_id,
        tier=tier,
        stripe_subscription_id=stripe_subscription_id,
        current_period_end=current_period_end,
        status=status_str,
        last_event_at=event_created_at,
        last_event_id=event_id,
    )
    row = (
        await session.exec(
            stmt.on_conflict_do_update(
                index_elements=[Subscription.user_id],
                set_={
                    "tier": stmt.excluded.tier,
                    "stripe_subscription_id": stmt.excluded.stripe_subscription_id,
                    "current_period_end": stmt.excluded.current_period_end,
                    "status": stmt.excluded.status,
                    "last_event_at": stmt.excluded.last_event_at,
                    "last_event_id": stmt.excluded.last_event_id,
                },
                where=tuple_(stmt.excluded.last_event_at, stmt.excluded.last_event_id)
                > tuple_(Subscription.last_event_at, Subscription.last_event_id),
            ).returning(Subscription.user_id)
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


async def get_user_tier(
    session: AsyncSession, *, user_id: UUID
) -> str:
    tier = (
        await session.exec(select(Subscription.tier).where(Subscription.user_id == user_id))
    ).first()
    return tier or "free"
