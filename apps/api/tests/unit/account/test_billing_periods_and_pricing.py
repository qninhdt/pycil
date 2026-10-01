"""Unit tests for calendar month periods and pricing unit conversions."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pycil.billing.periods import period_containing
from pycil.billing.units import (
    UNITS_PER_ALLOWANCE_UNIT,
    USD_PER_ALLOWANCE_UNIT,
    allowance_to_units,
    units_to_allowance,
    usd_to_units,
)

# --- Period Calendar Arithmetic Tests ---


def test_period_regular_calendar_month():
    anchor = datetime(2026, 3, 15, 9, 30, tzinfo=UTC)
    moment = datetime(2026, 3, 20, 12, 0, tzinfo=UTC)
    start, end = period_containing(anchor, moment)
    assert start == datetime(2026, 3, 15, 9, 30, tzinfo=UTC)
    assert end == datetime(2026, 4, 15, 9, 30, tzinfo=UTC)


def test_period_january_31_to_february_28_and_march_31():
    anchor = datetime(2026, 1, 31, 0, 0, tzinfo=UTC)

    # In February (short non-leap month)
    moment_feb = datetime(2026, 2, 10, tzinfo=UTC)
    start_feb, end_feb = period_containing(anchor, moment_feb)
    assert start_feb == datetime(2026, 1, 31, tzinfo=UTC)
    assert end_feb == datetime(2026, 2, 28, tzinfo=UTC)

    # In March: anchor restores to 31st
    moment_mar = datetime(2026, 3, 15, tzinfo=UTC)
    start_mar, end_mar = period_containing(anchor, moment_mar)
    assert start_mar == datetime(2026, 2, 28, tzinfo=UTC)
    assert end_mar == datetime(2026, 3, 31, tzinfo=UTC)

    # In April: 30 days
    moment_apr = datetime(2026, 4, 15, tzinfo=UTC)
    start_apr, end_apr = period_containing(anchor, moment_apr)
    assert start_apr == datetime(2026, 3, 31, tzinfo=UTC)
    assert end_apr == datetime(2026, 4, 30, tzinfo=UTC)


def test_period_leap_year_february_29():
    anchor = datetime(2028, 1, 31, 10, 0, tzinfo=UTC)
    moment = datetime(2028, 2, 15, tzinfo=UTC)
    start, end = period_containing(anchor, moment)
    assert start == datetime(2028, 1, 31, 10, 0, tzinfo=UTC)
    assert end == datetime(2028, 2, 29, 10, 0, tzinfo=UTC)


def test_period_boundary_inclusivity():
    anchor = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)

    # Moment exactly on start
    start, end = period_containing(anchor, datetime(2026, 5, 1, 12, 0, tzinfo=UTC))
    assert start == datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    assert end == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    # Moment 1 microsecond before end
    start, end = period_containing(anchor, datetime(2026, 6, 1, 11, 59, 59, 999999, tzinfo=UTC))
    assert start == datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    assert end == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    # Moment exactly on end starts next period
    start, end = period_containing(anchor, datetime(2026, 6, 1, 12, 0, tzinfo=UTC))
    assert start == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def test_period_long_dormancy():
    anchor = datetime(2026, 1, 31, tzinfo=UTC)
    future = datetime(2031, 7, 15, tzinfo=UTC)
    start, end = period_containing(anchor, future)
    assert start <= future < end
    assert start == datetime(2031, 6, 30, tzinfo=UTC)
    assert end == datetime(2031, 7, 31, tzinfo=UTC)


def test_period_moment_before_anchor_raises():
    anchor = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    past = datetime(2026, 4, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="moment precedes usage cycle anchor"):
        period_containing(anchor, past)


def test_period_naive_datetime():
    anchor = datetime(2026, 3, 15, 9, 0)
    moment = datetime(2026, 3, 20, 10, 0)
    start, end = period_containing(anchor, moment)
    assert start == datetime(2026, 3, 15, 9, 0, tzinfo=UTC)
    assert end == datetime(2026, 4, 15, 9, 0, tzinfo=UTC)


# --- Pricing Unit Conversions Tests ---


def test_pricing_constants():
    assert UNITS_PER_ALLOWANCE_UNIT == 1_000
    assert USD_PER_ALLOWANCE_UNIT == Decimal("0.001")


def test_usd_to_units():
    # 1 Allowance Unit = 1000 units = USD 0.001 => 1 USD = 1,000,000 units
    assert usd_to_units(Decimal("0.001")) == 1_000
    assert usd_to_units(Decimal("1.00")) == 1_000_000
    assert usd_to_units(Decimal("0.000001")) == 1
    # Round half up test: 0.0000015 USD = 1.5 units -> 2 units
    assert usd_to_units(Decimal("0.0000015")) == 2
    # 0.0000014 USD = 1.4 units -> 1 unit
    assert usd_to_units(Decimal("0.0000014")) == 1
    # 0 USD = 0 units
    assert usd_to_units(Decimal("0")) == 0
    # Negative USD = 0 units
    assert usd_to_units(Decimal("-0.01")) == 0


def test_allowance_to_units():
    assert allowance_to_units(1) == 1_000
    assert allowance_to_units(10) == 10_000
    assert allowance_to_units(Decimal("2.5")) == 2_500


def test_units_to_allowance():
    assert units_to_allowance(1_000) == Decimal("1")
    assert units_to_allowance(2_500) == Decimal("2.5")
    assert units_to_allowance(0) == Decimal("0")
