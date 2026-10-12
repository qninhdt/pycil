from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fsrs_rs_python import DEFAULT_PARAMETERS, FSRS, MemoryState

from pycil.study.fsrs import next_state


@pytest.mark.parametrize("seconds,days", [(-1, 0), (0, 0), (86399, 0), (86400, 1), (172799, 1)])
def test_native_elapsed_days_are_floored_not_rounded(config, seconds, days):
    now = datetime(2026, 10, 11, tzinfo=UTC)
    memory = SimpleNamespace(
        stability=20, difficulty=5, last_exposure_at=now - timedelta(seconds=seconds)
    )
    branch = (
        FSRS(DEFAULT_PARAMETERS)
        .next_states(MemoryState(20, 5), config.learning.fsrs.desired_retention, days)
        .good
    )
    assert next_state(memory, [None, 1, 1], now, config) == (
        branch.memory.stability,
        branch.memory.difficulty,
        now + timedelta(days=min(branch.interval, config.learning.fsrs.max_interval_days)),
    )


@pytest.mark.parametrize("recalls,branch_name", [([0, 1], "again"), ([1, None], "good")])
def test_first_observed_review_uses_native_initialization(config, recalls, branch_name):
    now = datetime(2026, 10, 11, tzinfo=UTC)
    branch = getattr(
        FSRS(DEFAULT_PARAMETERS).next_states(None, config.learning.fsrs.desired_retention, 0),
        branch_name,
    )
    stability, difficulty, due = next_state(None, recalls, now, config)
    assert (stability, difficulty) == (branch.memory.stability, branch.memory.difficulty)
    assert due == now + timedelta(days=min(branch.interval, config.learning.fsrs.max_interval_days))


@pytest.mark.parametrize("existing", [False, True])
def test_all_null_keeps_memory_and_reschedules_from_the_new_exposure(config, existing):
    now = datetime(2026, 10, 11, tzinfo=UTC)
    memory = (
        SimpleNamespace(stability=7, difficulty=4, last_exposure_at=now - timedelta(days=2))
        if existing
        else None
    )
    stability, difficulty, due = next_state(memory, [None, None], now, config)
    assert (stability, difficulty) == ((7, 4) if existing else (1, 5))
    interval = FSRS(DEFAULT_PARAMETERS).next_interval(
        stability, config.learning.fsrs.desired_retention, 3
    )
    assert due == now + timedelta(days=interval)
