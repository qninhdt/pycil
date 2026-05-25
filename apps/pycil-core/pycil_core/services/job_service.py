"""Job service: enqueue generate_term + cost-dedup via Redis lock.

Per-user rate limit (5/hr) and global daily spend cap (`OPENROUTER_BUDGET_DAILY_USD`)
are enforced pre-enqueue against Redis counters.
"""
from __future__ import annotations

import json
import os
from uuid import UUID, uuid4

from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.config import get_settings
from pycil_core.services.redis_pool import get_redis

_LOCK_TTL_SECONDS = 600
_RATE_LIMIT_PER_HOUR = 5


def _today_budget_key() -> str:
    """UTC-day partitioned spend counter; matches worker.redis_helpers."""
    from datetime import datetime, timezone
    return f"openrouter:spend:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

# Lock-acquire-or-get Lua, mirroring worker.redis_helpers.
_LOCK_LUA = """
local current = redis.call('GET', KEYS[1])
if current then return current end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return ARGV[1]
"""


async def _arq_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(get_settings().redis_url))


def _redis() -> Redis:
    return get_redis()


async def _check_user_rate(redis: Redis, user_id: UUID) -> None:
    key = f"rl:gen_term:{user_id}"
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, 3600)
    if n > _RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "limit_per_hour": _RATE_LIMIT_PER_HOUR},
        )


async def _check_global_budget(redis: Redis) -> None:
    cap = float(os.environ.get("OPENROUTER_BUDGET_DAILY_USD", "20"))
    raw = await redis.get(_today_budget_key())
    spent = 0.0
    if raw is not None:
        try:
            spent = float(raw)
        except (TypeError, ValueError):
            spent = 0.0
    if spent >= cap:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "budget_exhausted", "spent_usd": spent, "cap_usd": cap},
        )


async def enqueue_generate_term(
    session: AsyncSession, user_id: UUID, term_id: int
) -> dict:
    redis = _redis()
    try:
        # Budget first: rejecting on rate after a budget-exhaust would consume
        # a slot from the user's hourly quota for a request that never ran.
        await _check_global_budget(redis)
        await _check_user_rate(redis, user_id)

        # Lock-or-get: cost-dedup across users adding the same term.
        lock_key = f"lock:generate_term:{term_id}"
        new_job_id = str(uuid4())
        result = await redis.eval(
            _LOCK_LUA, 1, lock_key, new_job_id, _LOCK_TTL_SECONDS
        )
        owner_job_id = (
            result.decode() if isinstance(result, bytes) else str(result)
        )

        if owner_job_id != new_job_id:
            # Existing in-flight job for this term — reuse its job_id but still
            # write a per-user user_term_jobs row so this user owns its SSE view.
            await session.execute(
                text(
                    """
                    INSERT INTO user_term_jobs (user_id, term_id, job_id)
                    VALUES (:uid, :tid, :jid)
                    ON CONFLICT (user_id, term_id) DO UPDATE SET job_id = :jid
                    """
                ),
                {"uid": user_id, "tid": term_id, "jid": owner_job_id},
            )
            await session.commit()
            return {"job_id": owner_job_id, "deduped": True}

        # Fresh job: insert jobs row + user_term_jobs.
        await session.execute(
            text(
                """
                INSERT INTO jobs (id, type, status, payload)
                VALUES (:id, 'generate_term', 'pending', :payload::jsonb)
                """
            ),
            {
                "id": new_job_id,
                "payload": json.dumps({"term_id": term_id}),
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO user_term_jobs (user_id, term_id, job_id)
                VALUES (:uid, :tid, :jid)
                ON CONFLICT (user_id, term_id) DO UPDATE SET job_id = :jid
                """
            ),
            {"uid": user_id, "tid": term_id, "jid": new_job_id},
        )
        await session.commit()

        pool = await _arq_pool()
        try:
            await pool.enqueue_job(
                "generate_term", term_id, new_job_id, _job_id=new_job_id
            )
        except Exception:
            # Orphan-cleanup: enqueue failed → release lock + mark job failed
            # so the user gets a clear error instead of a 10-minute spinner.
            await redis.delete(lock_key)
            await session.execute(
                text(
                    "UPDATE jobs SET status = 'failed', error = 'enqueue_failed',"
                    " updated_at = NOW() WHERE id = :id"
                ),
                {"id": new_job_id},
            )
            await session.commit()
            raise
        finally:
            await pool.close()

        return {"job_id": new_job_id, "deduped": False}
    finally:
        await redis.aclose()
