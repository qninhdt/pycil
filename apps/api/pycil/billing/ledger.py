"""Authoritative plan entitlement and usage metering service."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.billing.errors import (
    BillingInvariantError,
    FeatureNotAvailableError,
    InsufficientAllowanceError,
    UsageQuotaExhaustedError,
)
from pycil.billing.models import AccountPlan, UsageEvent, UsagePeriod
from pycil.billing.periods import period_containing
from pycil.billing.plans import FeatureKey, PlanKey, get_plan, has_feature
from pycil.billing.schemas import UsageAllowance, UsageSettlement
from pycil.platform.telemetry import (
    record_plan_transition,
    record_usage_idempotent_replay,
    record_usage_overage,
    record_usage_period_created,
    record_usage_recording_failure,
    record_usage_settled,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def get_or_create_account_plan(
    session: AsyncSession,
    user_id: UUID,
    *,
    moment: datetime | None = None,
) -> AccountPlan:
    """Return the user's AccountPlan, provisioning default Free plan if absent.

    Never mutates an existing record.
    """
    plan = await session.get(AccountPlan, user_id)
    if plan is not None:
        return plan

    current_time = _as_utc(moment or datetime.now(UTC))
    stmt = (
        pg_insert(AccountPlan)
        .values(
            user_id=user_id,
            plan_key=PlanKey.free.value,
            cycle_anchor=current_time,
            updated_at=current_time,
        )
        .on_conflict_do_nothing(index_elements=[AccountPlan.user_id])
    )
    await session.execute(stmt)
    await session.flush()

    plan = await session.get(AccountPlan, user_id)
    if plan is None:  # pragma: no cover
        raise BillingInvariantError("account_plan_not_created")
    return plan


async def get_or_create_usage_period(
    session: AsyncSession,
    user_id: UUID,
    *,
    moment: datetime | None = None,
    plan: AccountPlan | None = None,
) -> UsagePeriod:
    """Return the canonical UsagePeriod for the month containing `moment`.

    Created lazily on the first operation in a new period. Safe against concurrent
    creation via UNIQUE(user_id, period_start) and ON CONFLICT DO NOTHING.
    """
    current_time = _as_utc(moment or datetime.now(UTC))
    if plan is None:
        plan = await get_or_create_account_plan(session, user_id, moment=current_time)

    period_start, period_end = period_containing(plan.cycle_anchor, current_time)

    stmt = select(UsagePeriod).where(
        UsagePeriod.user_id == user_id,
        UsagePeriod.period_start == period_start,
    )
    period = await session.scalar(stmt)
    if period is not None:
        return period

    plan_key = PlanKey(plan.plan_key)
    allowance = get_plan(plan_key).monthly_allowance_units
    insert_stmt = (
        pg_insert(UsagePeriod)
        .values(
            user_id=user_id,
            plan_key=plan_key.value,
            period_start=period_start,
            period_end=period_end,
            allowance_units=allowance,
            used_units=0,
            created_at=current_time,
            updated_at=current_time,
        )
        .on_conflict_do_nothing(index_elements=[UsagePeriod.user_id, UsagePeriod.period_start])
    )
    await session.execute(insert_stmt)
    await session.flush()

    period = await session.scalar(stmt)
    if period is None:  # pragma: no cover
        raise BillingInvariantError("usage_period_not_created")

    record_usage_period_created(plan=plan.plan_key)
    return period


async def get_usage_allowance(
    session: AsyncSession,
    user_id: UUID,
    *,
    moment: datetime | None = None,
) -> UsageAllowance:
    """Return the user's usage allowance for the period containing `moment`."""
    current_time = _as_utc(moment or datetime.now(UTC))
    plan = await get_or_create_account_plan(session, user_id, moment=current_time)
    period = await get_or_create_usage_period(session, user_id, moment=current_time, plan=plan)
    return UsageAllowance(
        plan=PlanKey(period.plan_key),
        period_id=period.id,
        period_start=period.period_start,
        period_end=period.period_end,
        allowance_units=period.allowance_units,
        used_units=period.used_units,
        remaining_units=period.remaining_units,
    )


async def require_usage_allowed(
    session: AsyncSession,
    user_id: UUID,
    *,
    feature: FeatureKey,
    required_units: int = 1,
    moment: datetime | None = None,
) -> UsageAllowance:
    """Enforce feature entitlement and usage quota availability.

    Raises:
        FeatureNotAvailableError: If feature is not entitled under the user's plan.
        InsufficientAllowanceError: If known required_units > 1 exceeds remaining usage.
        UsageQuotaExhaustedError: If required_units == 1 and no usage quota remains.
    """
    current_time = _as_utc(moment or datetime.now(UTC))
    plan = await get_or_create_account_plan(session, user_id, moment=current_time)
    plan_key = PlanKey(plan.plan_key)

    if not has_feature(plan_key, feature):
        raise FeatureNotAvailableError(
            f"Feature '{feature.value}' is not entitled under plan '{plan_key.value}'"
        )

    period = await get_or_create_usage_period(session, user_id, moment=current_time, plan=plan)
    remaining = period.remaining_units

    if required_units > 0 and remaining < required_units:
        if required_units > 1:
            raise InsufficientAllowanceError(
                f"Feature requires {required_units} units, but only {remaining} units remaining"
            )
        raise UsageQuotaExhaustedError("Usage quota is exhausted")

    return UsageAllowance(
        plan=plan_key,
        period_id=period.id,
        period_start=period.period_start,
        period_end=period.period_end,
        allowance_units=period.allowance_units,
        used_units=period.used_units,
        remaining_units=remaining,
    )


async def record_usage(
    session: AsyncSession,
    *,
    user_id: UUID,
    period_id: UUID,
    event_key: str,
    feature_key: FeatureKey,
    units: int,
    occurred_at: datetime | None = None,
    details: dict | None = None,
) -> UsageSettlement:
    """Atomically record metered usage for a feature event and increment used_units.

    Idempotent: retrying with the same event_key returns the existing settlement
    without incrementing used_units again.
    """
    if units <= 0:
        raise BillingInvariantError("units must be greater than zero")

    occ_time = _as_utc(occurred_at or datetime.now(UTC))

    insert_stmt = (
        pg_insert(UsageEvent)
        .values(
            period_id=period_id,
            event_key=event_key,
            feature_key=feature_key.value,
            units=units,
            occurred_at=occ_time,
            details=details,
        )
        .on_conflict_do_nothing(index_elements=[UsageEvent.event_key])
        .returning(UsageEvent.id)
    )

    try:
        inserted_id = (await session.execute(insert_stmt)).scalar_one_or_none()
    except Exception:
        record_usage_recording_failure(kind=feature_key.value)
        raise

    if inserted_id is None:
        # Replay: check existing event
        existing = (
            await session.execute(select(UsageEvent).where(UsageEvent.event_key == event_key))
        ).scalar_one_or_none()

        if existing is None:  # pragma: no cover
            record_usage_recording_failure(kind=feature_key.value)
            raise BillingInvariantError("conflict_without_existing_event")

        if (
            existing.period_id != period_id
            or existing.feature_key != feature_key.value
            or existing.units != units
        ):
            record_usage_recording_failure(kind=feature_key.value)
            raise BillingInvariantError("event key reused with different settlement payload")

        record_usage_idempotent_replay(kind=feature_key.value)
        return UsageSettlement(
            event_id=existing.id,
            event_key=event_key,
            period_id=period_id,
            feature_key=feature_key,
            units=units,
            idempotent_replay=True,
        )

    # First time insertion: update used_units in period with boundary checks
    update_stmt = (
        update(UsagePeriod)
        .where(
            UsagePeriod.id == period_id,
            UsagePeriod.user_id == user_id,
            UsagePeriod.period_start <= occ_time,
            UsagePeriod.period_end > occ_time,
        )
        .values(
            used_units=UsagePeriod.used_units + units,
            updated_at=func.now(),
        )
        .returning(
            UsagePeriod.id,
            UsagePeriod.allowance_units,
            UsagePeriod.used_units,
            UsagePeriod.plan_key,
        )
    )
    updated_period = (await session.execute(update_stmt)).first()

    if updated_period is None:
        record_usage_recording_failure(kind=feature_key.value)
        raise BillingInvariantError(
            f"usage period {period_id} invalid or out of bounds for user {user_id} at {occ_time}"
        )

    _, allowance_units, used_units, plan_key = updated_period
    record_usage_settled(kind=feature_key.value, units=units)

    if used_units > allowance_units:
        record_usage_overage(plan=plan_key, units=used_units - allowance_units)

    return UsageSettlement(
        event_id=inserted_id,
        event_key=event_key,
        period_id=period_id,
        feature_key=feature_key,
        units=units,
        idempotent_replay=False,
    )


async def set_plan(
    session: AsyncSession,
    user_id: UUID,
    new_plan: PlanKey,
    *,
    moment: datetime | None = None,
) -> AccountPlan:
    """Transition user to a new plan.

    Updates current active period's allowance to the new plan allowance if higher.
    """
    current_time = _as_utc(moment or datetime.now(UTC))
    account_plan = await get_or_create_account_plan(session, user_id, moment=current_time)
    from_plan = account_plan.plan_key

    account_plan.plan_key = new_plan.value
    account_plan.updated_at = current_time
    session.add(account_plan)

    new_allowance = get_plan(new_plan).monthly_allowance_units
    update_stmt = (
        update(UsagePeriod)
        .where(
            UsagePeriod.user_id == user_id,
            UsagePeriod.period_start <= current_time,
            UsagePeriod.period_end > current_time,
        )
        .values(
            allowance_units=func.greatest(UsagePeriod.allowance_units, new_allowance),
            plan_key=new_plan.value,
            updated_at=current_time,
        )
    )
    await session.execute(update_stmt)
    record_plan_transition(from_plan=from_plan, to_plan=new_plan.value)
    await session.flush()
    return account_plan
