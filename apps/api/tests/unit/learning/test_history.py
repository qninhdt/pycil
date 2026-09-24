"""Pure bucket/carry-forward coverage for folder history."""

from datetime import UTC, date, datetime

from pycil.policy.history import MasteryObservation, daily_history


def test_daily_history_carries_a_pre_window_baseline_through_sparse_days():
    buckets = daily_history(
        date(2026, 7, 10),
        date(2026, 7, 12),
        {1: 40},
        [MasteryObservation(1, datetime(2026, 7, 11, 9, tzinfo=UTC), 70)],
    )

    assert [(item.day.isoformat(), item.reviewed, item.avg_mastery) for item in buckets] == [
        ("2026-07-10", 0, 40.0),
        ("2026-07-11", 1, 70.0),
        ("2026-07-12", 0, 70.0),
    ]


def test_daily_history_keeps_empty_windows_stable():
    buckets = daily_history(date(2026, 7, 10), date(2026, 7, 11), {}, [])

    assert [(item.reviewed, item.avg_mastery) for item in buckets] == [(0, 0.0), (0, 0.0)]
