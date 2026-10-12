"""Native FSRS-6 Memory updates; null recall only refreshes the exposure clock."""

from datetime import timedelta

from fsrs_rs_python import DEFAULT_PARAMETERS, FSRS, MemoryState


def next_state(memory, recalls, now, config):
    policy = config.learning.fsrs
    fsrs = FSRS(DEFAULT_PARAMETERS)
    observed = [r for r in recalls if r is not None]
    if observed:
        elapsed = (
            max(0, int((now - memory.last_exposure_at).total_seconds() // 86400)) if memory else 0
        )
        current = MemoryState(memory.stability, memory.difficulty) if memory else None
        states = fsrs.next_states(current, policy.desired_retention, elapsed)
        branch = states.again if 0 in observed else states.good
        stability, difficulty, interval = (
            branch.memory.stability,
            branch.memory.difficulty,
            branch.interval,
        )
    else:
        stability = memory.stability if memory else policy.initial_stability
        difficulty = memory.difficulty if memory else policy.initial_difficulty
        # This pure interval calculation changes no Memory and records no Good observation.
        interval = fsrs.next_interval(stability, policy.desired_retention, 3)
    return stability, difficulty, now + timedelta(days=min(interval, policy.max_interval_days))
