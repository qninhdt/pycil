"""Shared lock-or-get + arq enqueue helper used by job/question services.

Extracts the common "atomic lock + (on lock-owner) enqueue arq job" body
that previously lived twice as 60+ LOC stretches in `job_service.py` and
`question_service.py`. Service-specific DB writes (jobs row, user_term_jobs
row, dedup behavior) remain in the callers — only the lock + arq-pool
plumbing is centralized.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from arq.connections import RedisSettings, create_pool
from redis.asyncio import Redis

from pycil_core.config import get_settings
from shared.redis_lock import LOCK_LUA


async def acquire_lock_or_get_owner(
    redis: Redis, *, lock_key: str, ttl_seconds: int
) -> tuple[str, str, bool]:
    """Atomically claim or read the lock holder.

    Returns (new_job_id, owner_job_id, is_owner). When `is_owner` is False
    the caller MUST treat `owner_job_id` as the existing in-flight job and
    skip its enqueue side-effects.
    """
    new_job_id = str(uuid4())
    raw = await redis.eval(LOCK_LUA, 1, lock_key, new_job_id, ttl_seconds)  # type: ignore[arg-type]
    owner = raw.decode() if isinstance(raw, bytes) else str(raw)
    return new_job_id, owner, owner == new_job_id


async def enqueue_arq_job(job_name: str, *args: Any, _job_id: str) -> None:
    """Open an arq pool, enqueue the job, then close the pool.

    Tied to per-request semantics for safety; lifespan-scoped pooling is a
    separate optimization tracked outside this helper.
    """
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job(job_name, *args, _job_id=_job_id)
    finally:
        await pool.close()
