"""Datetime mathematics, calendar intervals, and timezone conversions."""

from calendar import monthrange
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Return the current timezone-aware datetime in UTC."""
    return datetime.now(UTC)


def to_local_date(moment: datetime, tz_name: str) -> date:
    """Convert a UTC or timezone-aware datetime to a localized calendar date."""
    return moment.astimezone(ZoneInfo(tz_name)).date()


def date_range(start: date, end: date) -> Iterator[date]:
    """Yield each calendar date from start to end inclusive."""
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def period_bounds(anchor: datetime, moment: datetime) -> tuple[datetime, datetime]:
    """Calculate the start and end of a recurring monthly period anchored to a specific date."""
    anchor_utc = anchor.astimezone(UTC)
    moment_utc = moment.astimezone(UTC)
    index = (moment_utc.year - anchor_utc.year) * 12 + moment_utc.month - anchor_utc.month

    def boundary(offset: int) -> datetime:
        year, month = divmod(anchor_utc.year * 12 + anchor_utc.month - 1 + offset, 12)
        month += 1
        return anchor_utc.replace(
            year=year, month=month, day=min(anchor_utc.day, monthrange(year, month)[1])
        )

    if moment_utc < boundary(index):
        index -= 1
    return boundary(index), boundary(index + 1)


def resolve_date_window(
    start: date | None,
    end: date | None,
    today: date,
    max_days: int,
    *,
    future: bool = False,
) -> tuple[date, date]:
    """Resolve and validate a date range bounded by maximum calendar days."""
    if (start is None) != (end is None):
        raise ValueError("start and end dates must be provided or omitted together")
    if start is None:
        start, end = (
            (today, today + timedelta(days=max_days - 1))
            if future
            else (today - timedelta(days=max_days - 1), today)
        )
    assert start is not None and end is not None
    if end < start or (end - start).days >= max_days or (future and start < today):
        raise ValueError("invalid date window range")
    return start, end
