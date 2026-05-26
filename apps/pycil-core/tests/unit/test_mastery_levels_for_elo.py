"""Boundary tests for `mastery_levels.level_for_elo`.

Every bucket boundary asserted explicitly so a future tweak (rebalance,
narrowing, widening) breaks visibly. Also pins `MASTERY_LABELS`
completeness and the "Unknown" fallback.
"""
from __future__ import annotations

import pytest

from pycil_core.learning.mastery_levels import (
    MASTERY_LABELS,
    label_for_level,
    level_for_elo,
)


@pytest.mark.parametrize(
    "elo, expected",
    [
        (0, 1),
        (-1, 1),
        (799, 1),
        (800, 2),
        (899, 2),
        (900, 3),
        (999, 3),
        (1000, 4),
        (1099, 4),
        (1100, 5),
        (1199, 5),
        (1200, 6),
        (1299, 6),
        (1300, 7),
        (1399, 7),
        (1400, 8),
        (1499, 8),
        (1500, 9),
        (1599, 9),
        (1600, 10),
        (3000, 10),
        (10_000, 10),
    ],
)
def test_level_for_elo_boundaries(elo: int, expected: int) -> None:
    assert level_for_elo(elo) == expected


def test_mastery_labels_have_every_bucket() -> None:
    assert set(MASTERY_LABELS.keys()) == set(range(11))


def test_label_for_level_unknown_fallback() -> None:
    assert label_for_level(99) == "Unknown"
    assert label_for_level(-1) == "Unknown"
    # Known levels resolve normally.
    assert label_for_level(0) == "Unseen"
    assert label_for_level(10) == "Expert"
