"""One retry schedule, and the two clamping bugs converging on it removed.

Three sites had three policies, and the differences were accidents:

- `jobs/service.py` indexed `(5, 30, 120)` as `delays[attempt - 1]` with no clamp at
  all, against a `max_attempts` column defaulting to 4.
- `tasks/service.py` clamped in two places with two different expressions, one of
  which omitted the lower bound — so an attempt of 0 indexed `[-1]` and waited the
  LONGEST delay instead of the shortest.
- the CAS loops in `session_store.py` had no backoff whatsoever.

The tests below pin the schedule's edges rather than its middle, because every one of
those bugs was an edge.
"""

from __future__ import annotations

import asyncio
import random
import time

import pytest

from pycil.common.retry import (
    CAS_MAX_DELAY_SECONDS,
    RETRY_DELAYS_SECONDS,
    cas_backoff,
    next_attempt_delay,
)


def test_the_schedule_is_monotonic_and_starts_fast():
    """A first retry should be almost immediate — most first failures are a lost race
    or a cold dependency — and each subsequent one strictly longer."""
    assert RETRY_DELAYS_SECONDS[0] == 1
    assert list(RETRY_DELAYS_SECONDS) == sorted(RETRY_DELAYS_SECONDS)
    assert len(set(RETRY_DELAYS_SECONDS)) == len(RETRY_DELAYS_SECONDS)


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(1, 1), (2, 5), (3, 30), (4, 120), (5, 300)],
)
def test_each_attempt_maps_to_its_own_delay(attempt, expected):
    assert next_attempt_delay(attempt) == expected


def test_an_attempt_past_the_table_holds_at_the_longest_delay():
    """The bug in `jobs/service.py`: `delays[attempt - 1]` with a 3-entry table and a
    `max_attempts` of 4 is one configuration change from IndexError. A schedule running
    out is not a reason to strand an otherwise-retryable row."""
    last = RETRY_DELAYS_SECONDS[-1]
    for attempt in (len(RETRY_DELAYS_SECONDS), 6, 7, 99, 10_000):
        assert next_attempt_delay(attempt) == last


def test_attempt_zero_gets_the_shortest_delay_not_the_longest():
    """The bug in `resolve_outbox`: `min(attempt - 1, len - 1)` without `max(..., 0)`
    means attempt 0 indexes `[-1]`, so a row that had never been tried waited 300
    seconds instead of 1. Off by the entire width of the table."""
    assert next_attempt_delay(0) == RETRY_DELAYS_SECONDS[0]
    assert next_attempt_delay(-1) == RETRY_DELAYS_SECONDS[0]
    assert next_attempt_delay(-99) == RETRY_DELAYS_SECONDS[0]


def test_no_attempt_can_raise_for_any_table_size():
    """The property the clamp exists for: indexing must be total.

    Checked against a deliberately short table, since that is the shape that produced
    the original bug.
    """
    for table in ((7,), (1, 2), RETRY_DELAYS_SECONDS):
        for attempt in range(-5, 25):
            delay = next_attempt_delay(attempt, table)
            assert delay in table


# --- CAS backoff --------------------------------------------------------------


async def test_the_first_pass_through_a_cas_loop_is_free():
    """Callers pass their raw loop counter, so the uncontended path must not sleep —
    an added delay on every successful CAS would slow down the common case."""
    started = time.perf_counter()
    await cas_backoff(0)
    assert time.perf_counter() - started < 0.001


async def test_backoff_grows_with_contention_and_stays_capped():
    """Measured through the sampled delay rather than the sleep, so the assertion does
    not depend on the scheduler's timing."""
    # `random.uniform(0, delay)` is what is slept; drive it to its maximum so the
    # growth is observable exactly.
    class _Max(random.Random):
        def uniform(self, a: float, b: float) -> float:
            self.last = b
            return 0.0

    rng = _Max()
    seen = []
    for attempt in range(1, 12):
        await cas_backoff(attempt, rng=rng)
        seen.append(rng.last)

    assert seen == sorted(seen), seen
    assert max(seen) <= CAS_MAX_DELAY_SECONDS
    # And it actually reaches the cap rather than growing forever.
    assert seen[-1] == CAS_MAX_DELAY_SECONDS


async def test_the_delay_is_jittered_not_fixed():
    """Two writers that collided are running in step by definition, so a deterministic
    delay makes them collide again on the next tick. Sampling from [0, delay] is what
    breaks the lockstep."""

    class _Record(random.Random):
        """Records what was sampled, and sleeps zero so the test stays fast."""

        def __init__(self) -> None:
            super().__init__()
            self.drawn: list[float] = []

        def uniform(self, a: float, b: float) -> float:
            self.drawn.append(super().uniform(a, b))
            return 0.0

    samples = set()
    for _ in range(40):
        recorder = _Record()
        await cas_backoff(5, rng=recorder)
        samples.add(recorder.drawn[0])

    # Fixed delays would collapse to a single value.
    assert len(samples) > 1


async def test_a_contended_loop_finishes_rather_than_spinning():
    """The behaviour the backoff is for: bounded total delay under heavy contention.

    Ten collisions must still cost well under a second, or a busy session would stall
    a request that is otherwise about to succeed.
    """
    started = time.perf_counter()
    for attempt in range(1, 11):
        await cas_backoff(attempt)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5, elapsed


async def test_backoff_yields_control_to_the_event_loop():
    """A CAS retry has to let the writer that won actually finish. Sleeping zero would
    still yield; busy-looping would not."""
    order: list[str] = []

    async def _other():
        order.append("other")

    task = asyncio.ensure_future(_other())
    await cas_backoff(1)
    order.append("backoff-returned")
    await task

    assert order == ["other", "backoff-returned"]
