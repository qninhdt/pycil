"""Native FSRS-6 Memory updates; null recall only refreshes the exposure clock."""

from collections.abc import Sequence
from datetime import datetime, timedelta

from fsrs_rs_python import DEFAULT_PARAMETERS, FSRS, MemoryState

from pycil.app.config import AppConfig
from pycil.study.models import UserSense

_DEFAULT_FSRS = FSRS(DEFAULT_PARAMETERS)


def next_state(
    memory: UserSense | None,
    recalls: Sequence[int | float | None],
    now: datetime,
    config: AppConfig,
) -> tuple[float, float, datetime]:
    policy = config.product.study.fsrs
    fsrs = _DEFAULT_FSRS
    observed = [r for r in recalls if r is not None]
    if observed:
        elapsed = max(0, (now - memory.last_exposure_at).days) if memory else 0
        current = MemoryState(memory.stability, memory.difficulty) if memory else None
        states = fsrs.next_states(current, policy.desired_retention, elapsed)
        branch = states.again if 0 in observed else states.good
        stability: float = branch.memory.stability
        difficulty: float = branch.memory.difficulty
        interval: float = branch.interval
    else:
        stability = memory.stability if memory else policy.initial_stability
        difficulty = memory.difficulty if memory else policy.initial_difficulty
        # This pure interval calculation changes no Memory and records no Good observation.
        interval = int(fsrs.next_interval(stability, policy.desired_retention, 3))
    return stability, difficulty, now + timedelta(days=min(interval, policy.max_interval_days))
