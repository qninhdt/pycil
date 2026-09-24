"""Pure depth-axis transition rules."""

from __future__ import annotations

from typing import Final

MAX_DEPTH: Final = 4
DEPTH_FLOOR: Final = 1
PASSES_TO_ADVANCE: Final = 2


def next_depth_state(
    depth_level: int,
    depth_streak: int,
    served_level: int,
    correct: bool,
) -> tuple[int, int]:
    """Return ``(depth_level, depth_streak)`` after one graded answer.

    Depth zero is the unassessed state. Its first grade enters level one regardless
    of verdict; a correct level-one answer records the first clean pass there.
    """
    if depth_level <= 0:
        return 1, 1 if correct and served_level == 1 else 0

    level = max(DEPTH_FLOOR, min(MAX_DEPTH, depth_level))
    if not correct:
        return max(DEPTH_FLOOR, level - 1), 0

    if served_level != level:
        return level, max(0, depth_streak)

    if level == MAX_DEPTH:
        return MAX_DEPTH, 0

    streak = max(0, depth_streak) + 1
    if streak >= PASSES_TO_ADVANCE:
        return level + 1, 0
    return level, streak
