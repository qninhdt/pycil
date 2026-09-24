"""Calendar-month credit periods.

A credit period is the half-open UTC interval ``[start, end)`` derived from the
account's own cycle, not a rolling 30-day timer. The anchor is the day-of-month
and time-of-day the account first started being billed, kept separately from the
current period's start: clamping alone would drift, because a period anchored on
the 31st would renew on the 28th of February and then stay on the 28th forever.
Deriving every boundary from the anchor keeps the cycle stable. These functions
are pure so the rollover can be reasoned about and tested without a database.
"""

from calendar import monthrange
from datetime import UTC, datetime

#: The highest day-of-month any month can have, so a clamped anchor is only ever
#: shortened by a short month and never by the anchor itself.
MAX_ANCHOR_DAY = 31


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _shift_months(anchor: datetime, months: int) -> datetime:
    """``anchor`` advanced by whole months, its day clamped to that month's length.

    The clamp applies to the returned instant only. The caller keeps passing the
    original anchor, so a 31st-anchored account renews on the 31st again as soon
    as a month has one.
    """
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


def period_end(anchor: datetime, *, months_elapsed: int = 0) -> datetime:
    """Exclusive end of the period that began ``months_elapsed`` months after ``anchor``."""
    return _shift_months(_as_utc(anchor), months_elapsed + 1)


def current_period(anchor: datetime, now: datetime) -> tuple[datetime, int]:
    """The period start in effect at ``now``, and how many months it is from ``anchor``.

    A ``now`` before the anchor (only reachable if a clock moved backwards) is
    reported as the anchor with zero elapsed months, so a debit cannot silently
    reset usage.
    """
    start = _as_utc(anchor)
    moment = _as_utc(now)
    if moment < start:
        return start, 0

    # A year per probe first, then a month at a time, so an account untouched for
    # a decade resolves in a bounded number of steps instead of ~120.
    months = 0
    while _shift_months(start, months + 12) <= moment:
        months += 12
    while _shift_months(start, months + 1) <= moment:
        months += 1
    return _shift_months(start, months), months
