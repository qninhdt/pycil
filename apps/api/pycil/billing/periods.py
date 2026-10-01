"""Calendar-month usage period arithmetic.

All boundaries are derived from the user's stable usage cycle anchor using
exact calendar month arithmetic. Anchors are never permanently clamped by short
months: January 31 -> February 28/29 -> March 31.
"""

import calendar
from datetime import UTC, datetime


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _add_months_to_anchor(anchor: datetime, months: int) -> datetime:
    total_months = (anchor.year * 12 + (anchor.month - 1)) + months
    year = total_months // 12
    month = (total_months % 12) + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(anchor.day, max_day)
    return anchor.replace(year=year, month=month, day=day)


def period_containing(anchor: datetime, moment: datetime) -> tuple[datetime, datetime]:
    """Return (period_start, period_end) for the monthly period containing `moment`.

    The interval is half-open: `[period_start, period_end)`.
    Exact boundary `moment == period_end` selects the next period.
    `moment < anchor` raises ValueError.
    """
    utc_anchor = _as_utc(anchor)
    utc_moment = _as_utc(moment)

    if utc_moment < utc_anchor:
        raise ValueError("moment precedes usage cycle anchor")

    months = (utc_moment.year - utc_anchor.year) * 12 + (utc_moment.month - utc_anchor.month)

    start = _add_months_to_anchor(utc_anchor, months)
    if start > utc_moment:
        months -= 1
        start = _add_months_to_anchor(utc_anchor, months)

    end = _add_months_to_anchor(utc_anchor, months + 1)
    return start, end
