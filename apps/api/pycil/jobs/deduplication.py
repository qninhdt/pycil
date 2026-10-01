"""Redis Singleflight for deduplicating concurrent word generation tasks.

The mutual exclusion is `redis.asyncio.Lock`, not a hand-rolled `SET NX` plus a Lua
release. The lock is redis-py's own implementation of exactly that pattern —
compare-token-then-delete on release, so a holder that overran its TTL cannot
delete the next holder's lock — and it brings the blocking wait with it. The
previous version reimplemented both: a `SET NX PX` acquire, a copy of redis-py's
release script, and a one-second polling loop that made every waiter as slow as the
poll interval.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import LockError

from pycil.platform.product_config import system_config


def _wait_seconds() -> int:
    """How long a joining caller waits, owned by ``config/config.yaml``."""
    return system_config.content.singleflight_timeout_seconds


async def singleflight_generate_word(
    redis: Redis,
    query: str,
    generate_fn: Callable[[], Coroutine[Any, Any, dict]],
    fetch_existing_fn: Callable[[], Coroutine[Any, Any, dict]],
) -> dict:
    """Safeguards word generation so identical queries in flight do not duplicate LLM calls."""
    norm_query = query.lower().strip()
    lock = redis.lock(
        f"sf:word:{norm_query}:lock",
        timeout=_wait_seconds() * 2,
        blocking_timeout=_wait_seconds(),
    )
    status_key = f"sf:word:{norm_query}:status"

    # Non-blocking first, because whether this caller had to wait is what decides
    # if the status key below is a message for it. A caller that took the lock
    # outright is the one doing the work and must ignore a leftover status, or a
    # word generated a minute ago could never be regenerated.
    generating = await lock.acquire(blocking=False)
    if not generating and not await lock.acquire():
        raise TimeoutError(f"Word generation in flight timed out for {query}")

    try:
        if not generating:
            # Another caller owned the generation; wait for it, then read what it
            # left. The status distinguishes "committed, read the row" from
            # "failed", which would otherwise look like a word that does not exist.
            if await redis.get(status_key) in ("failed", b"failed"):
                raise RuntimeError(f"Concurrent word generation failed for {query}")
            return await fetch_existing_fn()

        try:
            result = await generate_fn()
        except Exception:
            await redis.set(status_key, "failed", ex=60)
            raise
        await redis.set(status_key, "done", ex=120)
        return result
    finally:
        try:
            await lock.release()
        except LockError:
            # The holder overran its TTL and the lock is someone else's now.
            # Releasing it would break their exclusion, and this caller is done.
            pass
