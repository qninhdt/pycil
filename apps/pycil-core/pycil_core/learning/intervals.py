"""Predefined review-interval ladder + nearest-snap helper.

Spaced-repetition systems benefit from a coarse, human-meaningful interval
ladder rather than letting `F^Δ/S` produce arbitrary fractional days. Snap
the computed interval to the nearest rung; this also caps growth at the top
rung (~2 months) which is plenty for v1.
"""
from __future__ import annotations

from bisect import bisect_left

_M = 60
_H = 60 * _M
_D = 24 * _H
_W = 7 * _D
_MO = 30 * _D

INTERVAL_LADDER_SECONDS: list[int] = [
    15 * _M, 30 * _M, 45 * _M,
    1 * _H, 2 * _H, 3 * _H, 4 * _H, 6 * _H, 8 * _H, 12 * _H,
    1 * _D, 2 * _D, 3 * _D, 4 * _D, 5 * _D, 6 * _D,
    1 * _W, 2 * _W, 3 * _W,
    1 * _MO, 2 * _MO,
]


def snap_to_ladder(seconds: float) -> int:
    """Return the closest rung. Below the floor → first rung."""
    if seconds <= INTERVAL_LADDER_SECONDS[0]:
        return INTERVAL_LADDER_SECONDS[0]
    if seconds >= INTERVAL_LADDER_SECONDS[-1]:
        return INTERVAL_LADDER_SECONDS[-1]
    idx = bisect_left(INTERVAL_LADDER_SECONDS, seconds)
    above = INTERVAL_LADDER_SECONDS[idx]
    below = INTERVAL_LADDER_SECONDS[idx - 1]
    return above if (above - seconds) < (seconds - below) else below
