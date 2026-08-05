"""One retry schedule for every durable retry site, and the CAS backoff.

Three separate policies existed before, and the differences between them were
accidents rather than decisions:

- `jobs/service.py`  had `(5, 30, 120)` and indexed it as `delays[attempt - 1]` with
  no clamp, against a `max_attempts` column defaulting to 4. That happens to be safe
  today only because the terminal check fires first at attempt 4. It is one row away
  from breaking: a job created with `max_attempts=6` raises IndexError while failing
  attempt 4, so `fail_generation` never commits and the row stays RUNNING with a
  cleared in-memory lease. It does eventually reach FAILED — `claim_generation`
  reclaims the expired lease and the `attempt >= max_attempts` check terminates it —
  but only after burning the remaining attempts on IndexErrors instead of recording
  the real `error_code`, and after a lease timeout each time instead of the intended
  backoff. The failure is silent and the diagnosis is wrong.
- `tasks/service.py` had `(1, 5, 30, 120, 300)` and did clamp, in two places, with two
  slightly different expressions.
- the 8 WATCH/MULTI CAS loops in `session_store.py` had no backoff at all: on contention
  they re-ran immediately, so several writers spun against each other as fast as the
  event loop allowed.

`next_attempt_delay` is the one schedule, always clamped, so adding an attempt can
never index past the end. `cas_backoff` is the spin control, with jitter, because
without it two writers retrying in lockstep collide again on the next tick.
"""

from __future__ import annotations

import asyncio
import random

# Durable retry schedule, in seconds, indexed by attempt.
#
# Starts at 1s because the first failure is usually a lost race or a cold dependency
# that clears immediately, and ends at 300s because anything still failing after five
# minutes needs a human rather than a tighter loop. Taken from the outbox table, which
# was the more considered of the two: it has the fast first retry that word generation
# lacked.
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
