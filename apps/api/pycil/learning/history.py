"""Stable daily mastery history built from immutable review-log observations."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class MasteryObservation:
    sense_id: int
    reviewed_at: datetime
    mastery_after: int


@dataclass(frozen=True)
class DailyHistoryBucket:
    day: date
    reviewed: int
    avg_mastery: float


def daily_history(
    start: date,
    end: date,
    baseline: dict[int, int],
    observations: Iterable[MasteryObservation],
) -> list[DailyHistoryBucket]:
    """Gap-fill daily buckets, carrying each learned sense's mastery forward.

    ``baseline`` is each sense's latest value strictly before ``start``. Events
    inside the window are applied in chronological order before that day's
    bucket is emitted, preserving a first day with no review event.
    """
    events: dict[date, list[MasteryObservation]] = defaultdict(list)
    for observation in observations:
        events[observation.reviewed_at.date()].append(observation)

    current = dict(baseline)
    buckets: list[DailyHistoryBucket] = []
    day = start
    while day <= end:
        day_events = events.get(day, [])
        for event in sorted(day_events, key=lambda item: item.reviewed_at):
            current[event.sense_id] = event.mastery_after
        average = round(sum(current.values()) / len(current), 2) if current else 0.0
        buckets.append(DailyHistoryBucket(day, len(day_events), average))
        day += timedelta(days=1)
    return buckets
