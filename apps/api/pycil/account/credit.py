"""The account credit ledger.

Submit paths call :func:`require_balance`; completion paths call :func:`debit`.
Keeping those operations separate makes provider failures free and makes retrying
a completed operation idempotent at the unique ledger key.

All amounts are integer milli-credits (1 Credit = 1,000 milli-credits = USD
0.001), so no float ever reaches SQL.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.models import CreditDebit, UserCredit
from pycil.account.periods import current_period, period_end
from pycil.account.plans import AccountPlan, normalize_plan, period_grant
from pycil.common.errors import ConflictError

#: Ledger entry kinds. ``rubric_grading`` is one fixed charge per successful
#: rubric provider evaluation. ``agent_turn`` settles an assistant turn from the
#: provider usage it actually reported, so its amount is always passed explicitly
#: rather than looked up from a table.
CREDIT_KIND_RUBRIC = "rubric_grading"
CREDIT_KIND_AGENT_TURN = "agent_turn"
CREDIT_KINDS = frozenset((CREDIT_KIND_RUBRIC, CREDIT_KIND_AGENT_TURN))


class CreditExhaustedError(ConflictError):
    """Typed refusal used at submit when an operation has no available credit."""

    def __init__(self) -> None:
        super().__init__("credit_exhausted", code="credit_exhausted")


@dataclass(frozen=True, slots=True)
class CreditSnapshot:
    plan: AccountPlan
    period_start: datetime
    period_end: datetime
    period_used: int
    topup_balance: int

    @property
    def grant(self) -> int:
        return period_grant(self.plan)

    @property
    def balance(self) -> int:
        """Signed allowance. A completed turn may have driven it below zero."""
        return self.grant - self.period_used + self.topup_balance

    @property
    def available(self) -> int:
        """The balance clamped for display, so the UI never shows a negative allowance."""
        return max(0, self.balance)

    def as_dict(self) -> dict:
        return {
            "plan": self.plan.value,
            "balance": self.balance,
            "available": self.available,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "period_used": self.period_used,
            "period_grant": self.grant,
            "topup_balance": self.topup_balance,
        }


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _positive_amount(amount: int, *, name: str = "amount") -> int:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError(f"{name}_must_be_positive")
    return amount


def _reference_id(reference_id: UUID | str) -> UUID:
    try:
        return reference_id if isinstance(reference_id, UUID) else UUID(str(reference_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("reference_id_must_be_uuid") from exc


async def _ensure_credit(
    session: AsyncSession, user_id: UUID, *, for_update: bool = False
) -> UserCredit:
    """Return the row, creating the default Free row if an older user lacks one."""
    statement = select(UserCredit).where(UserCredit.user_id == user_id)
    if for_update:
        statement = statement.with_for_update()
    row = await session.scalar(statement)
    if row is not None:
        return row

    # INSERT .. ON CONFLICT makes first use safe when two requests initialize the
    # same account at once.  The following SELECT obtains the lock used by debit.
    now = _now()
    await session.execute(
        insert(UserCredit)
        .values(
            user_id=user_id,
            plan=AccountPlan.free,
            period_anchor=now,
            period_start=now,
            period_used=0,
            topup_balance=0,
        )
        .on_conflict_do_nothing(index_elements=[UserCredit.user_id])
    )
    await session.flush()
    statement = select(UserCredit).where(UserCredit.user_id == user_id)
    if for_update:
        statement = statement.with_for_update()
    row = await session.scalar(statement)
    if row is None:  # pragma: no cover - the FK/PK transaction cannot omit it
        raise RuntimeError("credit_row_not_created")
    return row


def _effective_period(row: UserCredit, now: datetime) -> tuple[datetime, int, int]:
    """The period in effect at ``now``, as ``(start, months_from_anchor, used)``.

    The stored ``period_start`` is the start of the period ``period_used`` belongs
    to, so usage is preserved whenever the computed start has not moved past it.
    Recomputing from the anchor alone would be wrong: after the first debit of a
    new period the anchor still reports that one month has elapsed, and resetting
    on that basis would erase the usage just recorded.

    This writes nothing, so a read reflects a rolled-over period before the next
    debit persists it. Without that a fully-spent period that has since elapsed
    would keep reporting a zero balance, and the sampler that drops level 4 on a
    zero balance would never serve the level-4 answer whose debit is the only
    thing that rolls the period.
    """
    if row.period_start is None:  # server default is only absent before a flush
        raise RuntimeError("credit_period_start_missing")
    anchor = _as_utc(row.period_anchor or row.period_start)
    stored_start = _as_utc(row.period_start)
    computed_start, computed_months = current_period(anchor, now)
    if computed_start <= stored_start:
        # Still inside the stored period; report its own offset from the anchor so
        # the caller's period end matches the period the usage belongs to.
        return stored_start, current_period(anchor, stored_start)[1], row.period_used
    # A new period begins empty. The previous period's ledger rows are untouched
    # and keep pointing at the period they were charged in.
    return computed_start, computed_months, 0


def _roll_period(row: UserCredit, now: datetime) -> None:
    """Persist an elapsed-time rollover on the locked row before a debit."""
    row.period_start, _, row.period_used = _effective_period(row, now)


def _snapshot(row: UserCredit, now: datetime) -> CreditSnapshot:
    period_start, months_elapsed, period_used = _effective_period(row, now)
    anchor = _as_utc(row.period_anchor or period_start)
    return CreditSnapshot(
        plan=normalize_plan(row.plan),
        period_start=period_start,
        period_end=period_end(anchor, months_elapsed=months_elapsed),
        period_used=period_used,
        topup_balance=row.topup_balance,
    )


async def snapshot(
    session: AsyncSession, user_id: UUID, *, now: datetime | None = None
) -> CreditSnapshot:
    """Read one account's balance, reflecting (but not persisting) an elapsed roll."""
    row = await _ensure_credit(session, user_id)
    return _snapshot(row, _as_utc(now or _now()))


async def balance(session: AsyncSession, user_id: UUID) -> int:
    """Return the raw one-pool balance."""
    return (await snapshot(session, user_id)).balance


async def has_balance(session: AsyncSession, user_id: UUID, amount: int = 1) -> bool:
    amount = _positive_amount(amount)
    return (await snapshot(session, user_id)).balance >= amount


async def require_balance(session: AsyncSession, user_id: UUID, amount: int = 1) -> CreditSnapshot:
    """Enforce the positive submit-time balance gate."""
    amount = _positive_amount(amount)
    current = await snapshot(session, user_id)
    if current.balance < amount:
        raise CreditExhaustedError()
    return current


async def require_agent_credit(session: AsyncSession, user_id: UUID) -> CreditSnapshot:
    """Submit gate for one assistant turn: any positive balance admits it.

    This is a gate, not a price. The turn is billed on the provider usage it
    actually reports once it finishes, so a fixed minimum here would refuse a
    learner whose remaining allowance is small but sufficient. The learning path
    has no matching gate on purpose: exhausted credit degrades there (the sampler
    drops level 4) rather than refusing, so learning is never blocked.
    """
    return await require_balance(session, user_id, 1)


def _apply_debit(row: UserCredit, amount: int) -> None:
    """Consume period grant first, then top-up, preserving the one-pool formula."""
    grant = period_grant(row.plan)
    grant_remaining = max(0, grant - row.period_used)
    from_grant = min(amount, grant_remaining)
    row.period_used += from_grant

    remaining = amount - from_grant
    from_topup = min(remaining, max(0, row.topup_balance))
    row.topup_balance -= from_topup

    # Submit admission is the guard.  Concurrent admitted operations may finish
    # together, so a bounded completion overshoot is recorded in the current period
    # rather than silently dropping a provider call that already completed.
    row.period_used += remaining - from_topup


async def debit(
    session: AsyncSession,
    user_id: UUID,
    *,
    kind: str,
    reference_id: UUID | str,
    amount: int,
    now: datetime | None = None,
) -> CreditDebit:
    """Append one debit and apply its increment exactly once.

    ``amount`` is required because a rubric evaluation and an assistant turn are
    priced differently — one from configuration, the other from the provider usage
    a turn actually reported. A caller looking the amount up from a per-kind table
    is exactly the fixed-price coupling this signature removes.

    This function intentionally does not re-check availability: admission happened
    at submit, while completion must still charge a successful provider operation.
    The caller owns the surrounding transaction and commit.
    """
    if kind not in CREDIT_KINDS:
        raise ValueError("unknown_credit_kind")
    debit_amount = _positive_amount(amount)
    reference = _reference_id(reference_id)
    current_time = _as_utc(now or _now())

    row = await _ensure_credit(session, user_id, for_update=True)
    _roll_period(row, current_time)
    existing = await session.scalar(
        select(CreditDebit).where(CreditDebit.kind == kind, CreditDebit.reference_id == reference)
    )
    if existing is not None:
        if existing.user_id != user_id:
            raise ConflictError("credit_debit_reference_reused")
        if existing.amount != debit_amount:
            raise ConflictError("credit_debit_amount_mismatch")
        return existing

    inserted = await session.execute(
        insert(CreditDebit)
        .values(
            user_id=user_id,
            kind=kind,
            reference_id=reference,
            amount=debit_amount,
        )
        .on_conflict_do_nothing(index_elements=[CreditDebit.kind, CreditDebit.reference_id])
        .returning(CreditDebit.id)
    )
    debit_id = inserted.scalar_one_or_none()
    if debit_id is None:
        existing = await session.scalar(
            select(CreditDebit).where(
                CreditDebit.kind == kind, CreditDebit.reference_id == reference
            )
        )
        if existing is None:  # pragma: no cover - PostgreSQL unique conflict is atomic
            raise RuntimeError("credit_debit_conflict_without_row")
        if existing.user_id != user_id:
            raise ConflictError("credit_debit_reference_reused")
        if existing.amount != debit_amount:
            raise ConflictError("credit_debit_amount_mismatch")
        return existing

    _apply_debit(row, debit_amount)
    await session.flush()
    debit_row = await session.get(CreditDebit, debit_id)
    if debit_row is None:  # pragma: no cover - the inserted row is in this transaction
        raise RuntimeError("credit_debit_not_created")
    return debit_row


async def get_agent_turn(
    session: AsyncSession, user_id: UUID, reference_id: UUID | str
) -> CreditDebit | None:
    """Load a resumable assistant settlement owned by this learner."""
    reference = _reference_id(reference_id)
    row = await session.scalar(
        select(CreditDebit).where(
            CreditDebit.kind == CREDIT_KIND_AGENT_TURN,
            CreditDebit.reference_id == reference,
        )
    )
    if row is not None and row.user_id != user_id:
        raise ConflictError("credit_debit_reference_reused")
    return row


async def settle_agent_turn(
    session: AsyncSession,
    user_id: UUID,
    *,
    reference_id: UUID | str,
    amount: int,
    details: dict,
    now: datetime | None = None,
) -> CreditDebit:
    """Persist the cumulative amount for one assistant run, charging only its delta.

    An AG-UI approval pause can split a logical run across requests. Each pause
    persists the full reported usage snapshot under the same run UUID. Updating
    that row by the difference keeps one ledger entry for the run and makes a
    replay of the same snapshot a no-op.
    """
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise ValueError("amount_must_be_non_negative")
    reference = _reference_id(reference_id)
    current_time = _as_utc(now or _now())
    row = await _ensure_credit(session, user_id, for_update=True)
    _roll_period(row, current_time)
    period_key = _as_utc(row.period_start).isoformat()

    existing = await get_agent_turn(session, user_id, reference)
    if existing is not None:
        if amount < existing.amount:
            raise ConflictError("assistant_usage_regressed")
        delta = amount - existing.amount
        if delta:
            _apply_debit(row, delta)
        period_charges = dict((existing.details or {}).get("period_charges", {}))
        if delta:
            period_charges[period_key] = period_charges.get(period_key, 0) + delta
        existing.amount = amount
        existing.details = {
            **details,
            "period_charges": period_charges,
        }
        await session.flush()
        return existing

    period_charges = {period_key: amount} if amount else {}
    inserted = await session.execute(
        insert(CreditDebit)
        .values(
            user_id=user_id,
            kind=CREDIT_KIND_AGENT_TURN,
            reference_id=reference,
            amount=amount,
            details={**details, "period_charges": period_charges},
        )
        .on_conflict_do_nothing(index_elements=[CreditDebit.kind, CreditDebit.reference_id])
        .returning(CreditDebit.id)
    )
    debit_id = inserted.scalar_one_or_none()
    if debit_id is None:
        # The account-row lock serializes normal callers. This path handles a
        # Redis outage or a retry from another process that raced the unique key.
        existing = await get_agent_turn(session, user_id, reference)
        if existing is None:  # pragma: no cover - PostgreSQL conflict is atomic
            raise RuntimeError("assistant_debit_conflict_without_row")
        return await settle_agent_turn(
            session,
            user_id,
            reference_id=reference,
            amount=amount,
            details=details,
            now=current_time,
        )

    if amount:
        _apply_debit(row, amount)
    debit_row = await session.get(CreditDebit, debit_id)
    if debit_row is None:  # pragma: no cover - row is in this transaction
        raise RuntimeError("assistant_debit_not_created")
    return debit_row
