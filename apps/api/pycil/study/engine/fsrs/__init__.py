"""FSRS-4.5 spaced-repetition engine (pure math, no I/O).

The learning domain's single FSRS owner; the worker does not grade,
so it takes no dependency on this package.

Public API:
- ``initial_state(correct)`` / ``first_review(correct)`` — first-review memory state
- ``update(S, D, correct, elapsed_days)`` — post-review memory state
- ``next_state(S, D, correct, last_review, now)`` — post-review state with elapsed days calculation
- ``elapsed_days(last_review, now)`` — days between timestamps
- ``recall(S, elapsed_days)`` — retrievability probability
- ``mastery(S)`` — discrete 0-100 mastery
"""

from datetime import datetime

from pycil.study.engine.fsrs.engine import (
    GRADE_AGAIN,
    GRADE_GOOD,
    MemoryState,
    grade_from_correct,
    initial_state,
    update,
)
from pycil.study.engine.fsrs.mastery import mastery
from pycil.study.engine.fsrs.recall import recall


def elapsed_days(last_review: datetime | None, now: datetime) -> float:
    if last_review is None:
        return 0.0
    return max(0.0, (now - last_review).total_seconds() / 86400.0)


def next_state(
    stability: float, difficulty: float, correct: bool, last_review: datetime | None, now: datetime
) -> MemoryState:
    return update(stability, difficulty, correct, elapsed_days(last_review, now))


__all__ = [
    "GRADE_AGAIN",
    "GRADE_GOOD",
    "MemoryState",
    "elapsed_days",
    "grade_from_correct",
    "initial_state",
    "mastery",
    "next_state",
    "recall",
    "update",
]
