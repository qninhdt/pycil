"""Boundary tests for `intervals.snap_to_ladder`.

Pin behavior at every meaningful rung edge so future ladder edits surface
explicitly. Tie-break behavior (equidistant input) is documented in code:
`bisect_left` + `(above - x) < (x - below)` strict less-than → snaps to
the LOWER rung when distances are equal.
"""
from __future__ import annotations

import pytest

from pycil_core.learning.intervals import INTERVAL_LADDER_SECONDS, snap_to_ladder


_FLOOR = INTERVAL_LADDER_SECONDS[0]   # 15 min
_CEIL = INTERVAL_LADDER_SECONDS[-1]   # 2 months


@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0, _FLOOR),
        (1, _FLOOR),
        (_FLOOR - 1, _FLOOR),
        (_FLOOR, _FLOOR),
        (_FLOOR + 1, _FLOOR),
        (_CEIL, _CEIL),
        (_CEIL + 10**6, _CEIL),
    ],
)
def test_snap_at_extremes(seconds: float, expected: int) -> None:
    assert snap_to_ladder(seconds) == expected


def test_snap_lands_on_a_ladder_rung() -> None:
    """Every input in [floor, ceil] returns a value that's already on the ladder."""
    for s in [10 * 60, 17 * 60, 50 * 60, 90 * 60, 5 * 3600, 7 * 3600]:
        assert snap_to_ladder(s) in INTERVAL_LADDER_SECONDS


def test_snap_tie_chooses_lower_rung() -> None:
    """Tie-break: midpoint of two adjacent rungs snaps to the LOWER rung
    because the comparator is strict `<`, not `<=`.
    """
    floor = INTERVAL_LADDER_SECONDS[0]
    second = INTERVAL_LADDER_SECONDS[1]
    midpoint = (floor + second) / 2
    assert snap_to_ladder(midpoint) == floor


def test_snap_chooses_nearer_rung() -> None:
    floor = INTERVAL_LADDER_SECONDS[0]
    second = INTERVAL_LADDER_SECONDS[1]
    # Closer to the upper rung than the lower → upper.
    near_upper = floor + int((second - floor) * 0.9)
    assert snap_to_ladder(near_upper) == second
    # Closer to the lower rung → lower.
    near_lower = floor + int((second - floor) * 0.1)
    assert snap_to_ladder(near_lower) == floor
