from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fsrs_rs_python import DEFAULT_PARAMETERS, FSRS, MemoryState

from pycil.study.fsrs import next_state
from pycil.study.models import Rating


@pytest.mark.parametrize("seconds,days", [(-1, 0), (0, 0), (86399, 0), (86400, 1), (172799, 1)])
def test_native_elapsed_days_are_floored_not_rounded(config, seconds, days):
    now = datetime(2026, 10, 2, tzinfo=UTC)
    memory = SimpleNamespace(
        stability=20, difficulty=5, last_review_at=now - timedelta(seconds=seconds)
    )
    actual = next_state(memory, Rating.GOOD, now, config)
    branch = (
        FSRS(DEFAULT_PARAMETERS)
        .next_states(
            MemoryState(20, 5),
            config.learning.fsrs.desired_retention,
            days,
        )
        .good
    )
    assert actual == (
        branch.memory.stability,
        branch.memory.difficulty,
        now + timedelta(days=min(branch.interval, config.learning.fsrs.max_interval_days)),
    )


@pytest.mark.parametrize("rating", list(Rating))
def test_first_review_uses_no_memory_native_initialization(config, rating):
    now = datetime(2026, 10, 2, tzinfo=UTC)
    branch = getattr(
        FSRS(DEFAULT_PARAMETERS).next_states(
            None,
            config.learning.fsrs.desired_retention,
            0,
        ),
        rating.value.lower(),
    )
    stability, difficulty, due = next_state(None, rating, now, config)
    assert (stability, difficulty) == (branch.memory.stability, branch.memory.difficulty)
    assert due == now + timedelta(days=min(branch.interval, config.learning.fsrs.max_interval_days))
    assert due > now
