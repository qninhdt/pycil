"""Datetime mathematics, calendar intervals, and timezone conversions."""

from calendar import monthrange
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def to_local_date(moment: datetime, tz_name: str) -> date:
    """Convert a UTC or timezone-aware datetime to a localized calendar date."""
    return moment.astimezone(ZoneInfo(tz_name)).date()


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
