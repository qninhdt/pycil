"""Anchored monthly subscription units, with short serialized settlement."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.config import AccountConfig
from pycil.account.lifecycle import require_user
from pycil.account.models import UsageEvent, UsagePeriod, User
from pycil.account.plans import Feature, Plan
from pycil.account.types import AllowanceData
from pycil.infrastructure.database import transaction_lock
from pycil.observability import get_logger
from pycil.utils.dates import period_bounds
from pycil.utils.errors import Conflict, Forbidden, NotFound

logger = get_logger(__name__)


async def allowance(
    session: AsyncSession, user: User, config: AccountConfig, moment: datetime
) -> AllowanceData:
    start, end = period_bounds(user.cycle_anchor, moment)
    period = await session.scalar(
        select(UsagePeriod).where(
            UsagePeriod.user_id == user.id,
            UsagePeriod.period_start == start,
        )
    )
    permitted = config.plans[user.plan].monthly_allowance_units
    used = int(period.used_units) if period else 0
    budget = max(permitted, int(period.allowance_units)) if period else permitted
    return {
        "period_start": start,
        "period_end": end,
        "allowance_units": budget,
        "used_units": used,
        "remaining_units": max(0, budget - used),
    }


async def settle(
    session: AsyncSession,
    user_id: UUID,
    config: AccountConfig,
    *,
    execution_key: UUID,
    feature: Feature,
    units: int,
    unmetered_calls: int,
    moment: datetime,
) -> UsageEvent:
    if any(type(value) is not int or value < 0 for value in (units, unmetered_calls)):
        raise ValueError("invalid reported units")
    async with session.begin():
        await transaction_lock(session, f"usage-event:{execution_key}")
        await transaction_lock(session, f"usage:{user_id}")
        user = await require_user(session, user_id)
        existing = await session.scalar(
            select(UsageEvent).where(UsageEvent.execution_key == execution_key)
        )
        if existing:
            period = await session.get(UsagePeriod, existing.period_id)
            if (
                period is None
                or period.user_id != user_id
                or (
                    existing.feature,
                    existing.units,
                    existing.unmetered_calls,
                )
                != (feature, units, unmetered_calls)
            ):
                logger.warning(
                    "quota_settle_conflict",
                    user_id=str(user_id),
                    execution_key=str(execution_key),
                )
                raise Conflict("usage_event_conflict")
            return existing
        start, end = period_bounds(user.cycle_anchor, moment)
        period = await session.scalar(
            select(UsagePeriod).where(
                UsagePeriod.user_id == user_id,
                UsagePeriod.period_start == start,
            )
        )
        if period is None:
            period = UsagePeriod(
                user_id=user_id,
                period_start=start,
                period_end=end,
                allowance_units=config.plans[user.plan].monthly_allowance_units,
                used_units=0,
            )
            session.add(period)
            await session.flush()
        period.used_units += units
        event = UsageEvent(
            period_id=period.id,
            execution_key=execution_key,
            feature=feature,
            units=units,
            unmetered_calls=unmetered_calls,
            occurred_at=moment,
        )
        session.add(event)
        await session.flush()
        logger.info(
            "quota_units_settled",
            user_id=str(user_id),
            execution_key=str(execution_key),
            feature=feature.value,
            units=units,
        )
        return event


async def change_plan(
    session: AsyncSession,
    user_id: UUID,
    plan: Plan,
    config: AccountConfig,
    moment: datetime,
) -> None:
    async with session.begin():
        await transaction_lock(session, f"usage:{user_id}")
        user = await session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if user is None:
            raise NotFound("account_not_found")
        user.plan = plan
        start, _ = period_bounds(user.cycle_anchor, moment)
        period = await session.scalar(
            select(UsagePeriod).where(
                UsagePeriod.user_id == user_id,
                UsagePeriod.period_start == start,
            )
        )
        if period:
            period.allowance_units = max(
                period.allowance_units, config.plans[plan].monthly_allowance_units
            )
        logger.info("account_plan_changed", user_id=str(user_id), plan=plan.value)


async def admit(
    session: AsyncSession,
    user_id: UUID,
    config: AccountConfig,
    feature: Feature,
    moment: datetime,
) -> Plan:
    async with session.begin():
        user = await session.scalar(
            select(User).where(User.id == user_id).execution_options(populate_existing=True)
        )
        if user is None:
            raise NotFound("account_not_found")
        if feature not in config.plans[user.plan].features:
            logger.warning(
                "feature_access_denied",
                user_id=str(user_id),
                feature=feature.value,
                plan=user.plan.value,
            )
            raise Forbidden("feature_not_available")
        budget = await allowance(session, user, config, moment)
        remaining = int(budget["remaining_units"])
        if remaining <= 0:
            logger.warning(
                "quota_allowance_exhausted",
                user_id=str(user_id),
                feature=feature.value,
            )
            raise Forbidden("allowance_exhausted")
        return user.plan
