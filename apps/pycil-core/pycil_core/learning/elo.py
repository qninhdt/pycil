"""Pure ELO scoring math.

No I/O. Every function is a small pure transformation so unit tests can
exhaustively cover the formula edges (cold start, clamp bounds, lapsed-time
decay, interval growth on success vs hold-on-fail).

Constants from the project plan / idea.md §4.3:
- K=32, D=400, ALPHA=0.5, F=2.0, S=200
- ELO ∈ [0, 3000], INITIAL=1000
- Interval floor: 30 minutes (so multiplicative growth has a non-zero base
  on the very first review, when stored interval is 0).
"""
from __future__ import annotations

from statistics import mean

K = 32
D = 400
ALPHA = 0.5
F = 2.0
S = 200

INITIAL_ELO = 1000
MIN_ELO = 0
MAX_ELO = 3000

INITIAL_INTERVAL_SECONDS = 1800  # 30 minutes — see module docstring


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def realized_score(correct_first_count: int, q_required: int) -> float:
    """R = correct first-answers / Q-required. Bounded to [0, 1]."""
    if q_required <= 0:
        return 0.0
    return min(1.0, max(0.0, correct_first_count / q_required))


def expected_score_per_question(elo_user: int, elo_question: int) -> float:
    """Standard ELO expectation: 1 / (1 + 10^((Q-U)/D))."""
    return 1.0 / (1.0 + 10 ** ((elo_question - elo_user) / D))


def expected_score(elo_user: int, elo_questions: list[int]) -> float:
    """Average per-question expectation across the questions answered."""
    if not elo_questions:
        return 0.5
    return mean(
        expected_score_per_question(elo_user, q) for q in elo_questions
    )


def lapsed_time_factor(
    lapsed_seconds: float | None, interval_seconds: float
) -> float:
    """Cold-start safe lapsed-time decay.

    `lapsed_seconds=None` (no prior review) → T=1.0 (full weight). This is
    the bug fix vs naive `lapsed/interval` which would make the first review
    weight zero and never move ELO.
    """
    if lapsed_seconds is None or lapsed_seconds <= 0:
        return 1.0
    if interval_seconds <= 0:
        return 1.0
    return (lapsed_seconds / interval_seconds) ** ALPHA


def elo_delta(R: float, E: float, T: float) -> int:
    """Δ = round(K * (R - E) * T)."""
    return round(K * (R - E) * T)


def new_elo(elo_old: int, delta: int) -> int:
    """Apply delta and clamp to [MIN_ELO, MAX_ELO]."""
    return _clamp(elo_old + delta, MIN_ELO, MAX_ELO)


def new_interval_seconds(
    elo_old: int, elo_new: int, interval_old: float
) -> float:
    """Interval grows on success (F^Δ/S), holds on failure (Δ<0).

    First-review case: stored `interval_old=0` → floored at
    INITIAL_INTERVAL_SECONDS so the multiplicative growth has a non-zero base.
    """
    base = max(interval_old, INITIAL_INTERVAL_SECONDS)
    if elo_new < elo_old:
        return base
    return base * (F ** ((elo_new - elo_old) / S))
