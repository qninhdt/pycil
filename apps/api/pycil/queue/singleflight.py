"""Redis Singleflight for deduplicating concurrent word generation tasks."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis

from pycil.product_config import system_config

_RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


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
    lock_key = f"sf:word:{norm_query}:lock"
    status_key = f"sf:word:{norm_query}:status"
    lock_val = str(uuid4())
    wait_seconds = _wait_seconds()

    acquired = await redis.set(lock_key, lock_val, nx=True, ex=wait_seconds * 2)
    if not acquired:
        # Polling loop waiting for active generator worker to finish
        for _ in range(wait_seconds):
            await asyncio.sleep(1)
            status = await redis.get(status_key)
            if status == b"done":
                return await fetch_existing_fn()
            if status == b"failed":
                raise RuntimeError(f"Concurrent word generation failed for {query}")
        raise TimeoutError(f"Word generation in flight timed out for {query}")

    try:
        result = await generate_fn()
        await redis.set(status_key, "done", ex=120)
        return result
    except Exception:
        await redis.set(status_key, "failed", ex=60)
        raise
    finally:
        await redis.eval(_RELEASE_LUA, 1, lock_key, lock_val)
