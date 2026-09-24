"""Shared retry schedule for durable jobs and CAS contention backoff."""

from __future__ import annotations

import asyncio
import random

# Durable retry schedule, in seconds, indexed by attempt.
#
# Starts at 1s because the first failure is usually a lost race or a cold dependency
# that clears immediately, and ends at 300s because anything still failing after five
# minutes needs a human rather than a tighter loop. The schedule is shared by every
# durable job so retries have one owner.
RETRY_DELAYS_SECONDS: tuple[int, ...] = (1, 5, 30, 120, 300)


def next_attempt_delay(attempt: int, delays: tuple[int, ...] = RETRY_DELAYS_SECONDS) -> int:
    """Seconds to wait before ``attempt`` is retried. ``attempt`` is 1-based.

    Clamped at both ends. An attempt beyond the table holds at the longest delay
    rather than raising: a schedule running out is not a reason to strand a row that
    is otherwise retryable, and it is exactly the case the unclamped caller got wrong.
    """
    index = min(max(attempt - 1, 0), len(delays) - 1)
    return delays[index]


# CAS contention backoff. Deliberately sub-millisecond at the start: a WATCH/MULTI
# retry is a local round trip, so the first collision should cost almost nothing, and
# only sustained contention should slow a writer down.
CAS_BASE_DELAY_SECONDS = 0.002
CAS_MAX_DELAY_SECONDS = 0.05


async def cas_backoff(
    attempt: int,
    *,
    base: float = CAS_BASE_DELAY_SECONDS,
    cap: float = CAS_MAX_DELAY_SECONDS,
    rng: random.Random | None = None,
) -> None:
    """Sleep before re-running a CAS loop that lost its WATCH. ``attempt`` is 1-based.

    Exponential with full jitter, capped. The jitter is the point: two writers that
    collided are, by definition, running in step, so a deterministic delay makes them
    collide again on the next tick. Sampling uniformly from [0, delay] breaks that
    without adding meaningful latency.

    ``attempt <= 0`` sleeps not at all, so a caller can pass its raw loop counter and
    the first pass through the loop stays free.
    """
    if attempt <= 0:
        return
    picker = rng if rng is not None else random
    delay = min(cap, base * (2 ** (attempt - 1)))
    await asyncio.sleep(picker.uniform(0.0, delay))
