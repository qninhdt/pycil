"""Retrievability (recall probability) — FSRS-4.5 power-law forgetting curve.

R(t) = (1 + (19/81)·t/S)^(-0.5), so R = 0.9 exactly when t == S.
"""

_FACTOR = 19.0 / 81.0


def recall(stability: float, elapsed_days: float) -> float:
    """Probability of recall after ``elapsed_days`` given current stability.

    Returns 1.0 for a brand-new card (stability <= 0) with no elapsed time.
    """
    if stability <= 0:
        return 0.0
    return (1.0 + _FACTOR * elapsed_days / stability) ** -0.5
