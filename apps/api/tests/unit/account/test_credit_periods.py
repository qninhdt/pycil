"""Calendar-month credit periods, including the short-month cases.

The rollover is derived arithmetic rather than a stored timer, so the cases that
matter are the ones a fixed 30-day period gets wrong: month lengths that differ,
and an anchor day that does not exist in the target month. The anchor must also
survive a short month — a cycle anchored on the 31st has to return to the 31st
once a month has one, which is what separates anchoring from clamping.
"""

from datetime import UTC, datetime

from pycil.account.periods import current_period, period_end


def test_a_period_ends_one_calendar_month_later():
    anchor = datetime(2026, 3, 15, 9, 30, tzinfo=UTC)
    assert period_end(anchor) == datetime(2026, 4, 15, 9, 30, tzinfo=UTC)


def test_a_february_period_is_shorter_than_a_30_day_timer():
    """A 31-day month followed by February, which a day-count period cannot express."""
    anchor = datetime(2026, 1, 31, tzinfo=UTC)
    assert period_end(anchor) == datetime(2026, 2, 28, tzinfo=UTC)
    assert (period_end(anchor) - anchor).days == 28


def test_a_december_period_rolls_into_the_next_year():
    assert period_end(datetime(2026, 12, 20, tzinfo=UTC)) == datetime(2027, 1, 20, tzinfo=UTC)


def test_the_31st_is_clamped_only_for_months_that_lack_it():
    """A 31-day anchor must not be permanently shortened by February."""
    anchor = datetime(2026, 1, 31, tzinfo=UTC)
    assert period_end(anchor) == datetime(2026, 2, 28, tzinfo=UTC)
    # The anchor itself is unchanged, so the following month is the 31st again.
    assert period_end(anchor, months_elapsed=1) == datetime(2026, 3, 31, tzinfo=UTC)


def test_a_leap_february_uses_its_29th_day():
    anchor = datetime(2028, 1, 31, tzinfo=UTC)
    assert period_end(anchor) == datetime(2028, 2, 29, tzinfo=UTC)


def test_the_elapsed_month_count_advances_once_per_boundary():
    anchor = datetime(2026, 1, 31, tzinfo=UTC)
    # The clamped boundary is February 28, so a moment before it is period one.
    start, months = current_period(anchor, datetime(2026, 2, 27, 23, 59, 59, tzinfo=UTC))
    assert (start, months) == (anchor, 0)
    # At the boundary the second period begins.
    start, months = current_period(anchor, datetime(2026, 2, 28, tzinfo=UTC))
    assert (start, months) == (datetime(2026, 2, 28, tzinfo=UTC), 1)


def test_a_long_dormancy_resolves_without_drifting():
    anchor = datetime(2026, 1, 31, tzinfo=UTC)
    start, months = current_period(anchor, datetime(2030, 5, 15, tzinfo=UTC))
    assert months == 51
    assert start == datetime(2030, 4, 30, tzinfo=UTC)
    assert period_end(anchor, months_elapsed=months) > datetime(2030, 5, 15, tzinfo=UTC)


def test_a_clock_that_moved_backwards_does_not_reset_usage():
    """A `now` before the anchor must not be read as a fresh period."""
    anchor = datetime(2026, 6, 10, tzinfo=UTC)
    start, months = current_period(anchor, datetime(2026, 6, 1, tzinfo=UTC))
    assert (start, months) == (anchor, 0)


def test_a_naive_timestamp_is_read_as_utc():
    assert period_end(datetime(2026, 3, 15)) == datetime(2026, 4, 15, tzinfo=UTC)
