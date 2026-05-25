"""Tests for gamification_service: XP, streak, level math."""
from __future__ import annotations

import pytest

from pycil_core.services.gamification_service import (
    LEVEL_TABLE,
    XP_DELTA,
    compute_level,
)


def test_xp_delta_keys() -> None:
    """XP_DELTA must define all three reward kinds."""
    assert {"correct_new", "correct_review", "wrong"} == set(XP_DELTA.keys())
    assert XP_DELTA["correct_new"] > XP_DELTA["correct_review"] > XP_DELTA["wrong"]


@pytest.mark.parametrize(
    "xp,expected_level",
    [
        (0, 1),
        (99, 1),
        (100, 2),
        (250, 3),
        (1000, 5),
        (16_000, 10),
        (22_000, 11),
        (1_000_000, 11),  # caps at last entry in LEVEL_TABLE
    ],
)
def test_compute_level_table(xp: int, expected_level: int) -> None:
    assert compute_level(xp) == expected_level


def test_level_table_is_monotonic() -> None:
    thresholds = [t for _, t in LEVEL_TABLE]
    assert thresholds == sorted(thresholds)
    levels = [lvl for lvl, _ in LEVEL_TABLE]
    assert levels == sorted(levels)
