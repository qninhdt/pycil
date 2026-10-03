"""Small wrapper over the installed native binding, not another scheduling algorithm."""

from datetime import timedelta

from fsrs_rs_python import DEFAULT_PARAMETERS, FSRS, MemoryState

from pycil.study.models import Rating


def mastery(stability, config):
    return round(100 * stability / (stability + config.learning.fsrs.mastery_stability_scale_days))


def next_state(memory, rating, now, config):
    elapsed = max(0, int((now - memory.last_review_at).total_seconds() // 86400)) if memory else 0
    current = MemoryState(memory.stability, memory.difficulty) if memory else None
    states = FSRS(DEFAULT_PARAMETERS).next_states(
        current, config.learning.fsrs.desired_retention, elapsed
    )
    branch = {
        Rating.AGAIN: states.again,
        Rating.HARD: states.hard,
        Rating.GOOD: states.good,
        Rating.EASY: states.easy,
    }[rating]
    interval = min(branch.interval, config.learning.fsrs.max_interval_days)
    return branch.memory.stability, branch.memory.difficulty, now + timedelta(days=interval)
