"""FSRS-4.5 spaced-repetition engine (pure math, no I/O).

The learning domain's single FSRS owner. The API consumes it through
``pycil.learning.fsrs_wrapper``; the worker does not grade, so it takes
no dependency on this package.

Public API:
- ``initial_state(correct)`` — first-review memory state
- ``update(S, D, correct, elapsed_days)`` — post-review memory state
- ``recall(S, elapsed_days)`` — retrievability probability
- ``mastery(S)`` — discrete 0-100 mastery
"""

from pycil.learning.fsrs.engine import (
    GRADE_AGAIN,
    GRADE_GOOD,
    MemoryState,
    grade_from_correct,
    initial_state,
    update,
)
from pycil.learning.fsrs.mastery import mastery
from pycil.learning.fsrs.recall import recall

__all__ = [
    "GRADE_AGAIN",
    "GRADE_GOOD",
    "MemoryState",
    "grade_from_correct",
    "initial_state",
    "update",
    "mastery",
    "recall",
]
