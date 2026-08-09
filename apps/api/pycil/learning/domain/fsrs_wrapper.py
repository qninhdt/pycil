"""Thin wrapper over shared.fsrs — the learning domain's single FSRS entry point."""

from datetime import datetime

from shared.fsrs import MemoryState, initial_state, update


def elapsed_days(last_review: datetime | None, now: datetime) -> float:
    if last_review is None:
        return 0.0
    return max(0.0, (now - last_review).total_seconds() / 86400.0)


def first_review(correct: bool) -> MemoryState:
    return initial_state(correct)


def next_state(
    stability: float, difficulty: float, correct: bool, last_review: datetime | None, now: datetime
) -> MemoryState:
    return update(stability, difficulty, correct, elapsed_days(last_review, now))


__all__ = ["MemoryState", "elapsed_days", "first_review", "next_state"]
