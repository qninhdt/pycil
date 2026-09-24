"""FSRS-4.5 memory-state update — pure functions, no I/O.

The implementation follows pycil-redesign/modules/learning.md. The engine sees only a
binary label mapped to two FSRS grades: correct→Good(3), wrong→Again(1). Hard(2)
and Easy(4) are never emitted, so the weights tied to them are dead constants.
"""

import math
from dataclasses import dataclass

from pycil.learning.fsrs.recall import recall
from pycil.learning.fsrs.weights import W

GRADE_AGAIN = 1
GRADE_GOOD = 3

_MIN_INTERVAL_DAYS = 30.0 / (24.0 * 60.0)  # 30 minutes
_MAX_INTERVAL_DAYS = 365.0
_D_MIN = 1.0
_D_MAX = 10.0


@dataclass(frozen=True)
class MemoryState:
    stability: float
    difficulty: float
    interval_days: float


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def grade_from_correct(correct: bool) -> int:
    return GRADE_GOOD if correct else GRADE_AGAIN


def _init_difficulty(grade: int) -> float:
    # D0 = w4 - exp(w5·(grade-1)) + 1, clamped to [1,10].
    d0 = W[4] - math.exp(W[5] * (grade - 1)) + 1.0
    return _clamp(d0, _D_MIN, _D_MAX)


def _next_difficulty(difficulty: float, grade: int) -> float:
    # Linear delta (rises on Again, eases on Good) + mean-reversion toward D0(Good)
    # to prevent "ease hell". Standard FSRS difficulty update.
    delta = difficulty - W[6] * (grade - 3)
    target = _init_difficulty(GRADE_GOOD)
    reverted = W[7] * target + (1.0 - W[7]) * delta
    return _clamp(reverted, _D_MIN, _D_MAX)


def _interval(stability: float) -> float:
    return _clamp(stability, _MIN_INTERVAL_DAYS, _MAX_INTERVAL_DAYS)


def initial_state(correct: bool) -> MemoryState:
    """First-ever review: S0 from grade, D0 from grade."""
    grade = grade_from_correct(correct)
    stability = W[2] if correct else W[0]
    difficulty = _init_difficulty(grade)
    return MemoryState(stability, difficulty, _interval(stability))


def update(stability: float, difficulty: float, correct: bool, elapsed_days: float) -> MemoryState:
    """Update memory state after a review. Returns new (S, D, interval)."""
    grade = grade_from_correct(correct)
    r = recall(stability, elapsed_days)
    new_difficulty = _next_difficulty(difficulty, grade)

    if correct:
        # S' = S·(1 + exp(w8)·(11-D)·S^(-w9)·(exp(w10·(1-R)) - 1))
        factor = (
            math.exp(W[8])
            * (11.0 - difficulty)
            * (stability ** -W[9])
            * (math.exp(W[10] * (1.0 - r)) - 1.0)
        )
        new_stability = stability * (1.0 + factor)
    else:
        # S' = min(S, w11·D^(-w12)·((S+1)^w13 - 1)·exp(w14·(1-R)))
        failed = (
            W[11]
            * (difficulty ** -W[12])
            * (((stability + 1.0) ** W[13]) - 1.0)
            * math.exp(W[14] * (1.0 - r))
        )
        new_stability = min(stability, failed)

    return MemoryState(new_stability, new_difficulty, _interval(new_stability))
