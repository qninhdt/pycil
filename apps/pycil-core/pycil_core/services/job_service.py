"""Job service: enqueue generate_term + cost-dedup via Redis lock.

Per-user rate limit (5/hr) and global daily spend cap (`OPENROUTER_BUDGET_DAILY_USD`)
are enforced pre-enqueue against Redis counters.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from shared.redis_lock import spend_key_today
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.services._job_enqueue import (
    acquire_lock_or_get_owner,
    enqueue_arq_job,
)
from pycil_core.services.redis_pool import get_redis

_LOCK_TTL_SECONDS = 600
_RATE_LIMIT_PER_HOUR = 5


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
    import os
    cap = float(os.environ.get("OPENROUTER_BUDGET_DAILY_USD", "20"))
    raw = await redis.get(spend_key_today())
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
    session: AsyncSession,
    user_id: UUID,
    term_id: int,
    *,
    skip_user_rate: bool = False,
) -> dict:
    """Enqueue an enrichment job. `skip_user_rate=True` is for batch ingestion
    paths that already enforce their own per-min/per-day quotas — the per-user
    5/hr cap was sized for "user types one term" and would 429 mid-batch."""
    redis = _redis()
    try:
        # Budget first: rejecting on rate after a budget-exhaust would consume
        # a slot from the user's hourly quota for a request that never ran.
        await _check_global_budget(redis)
        if not skip_user_rate:
            await _check_user_rate(redis, user_id)

        # Lock-or-get: cost-dedup across users adding the same term.
        lock_key = f"lock:generate_term:{term_id}"
        new_job_id, owner_job_id, is_owner = await acquire_lock_or_get_owner(
            redis, lock_key=lock_key, ttl_seconds=_LOCK_TTL_SECONDS
        )

        if not is_owner:
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

        # Fresh job: insert jobs row + user_term_jobs, then enqueue.
        # Any failure AFTER we acquired the lock must release it — otherwise
        # this term is un-enrichable for the full TTL window. Previously only
        # the enqueue failure released the lock; a commit failure on the INSERTs
        # (unique violation, deadlock, dropped conn) leaked it.
        try:
            await session.execute(
                text(
                    """
                    INSERT INTO jobs (id, type, status, payload)
                    VALUES (:id, 'generate_term', 'pending', CAST(:payload AS jsonb))
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

            await enqueue_arq_job(
                "generate_term", term_id, new_job_id, _job_id=new_job_id
            )
        except Exception:
            # Orphan-cleanup: release lock so the user gets a clear error
            # instead of a 10-minute spinner. Then best-effort mark the job
            # failed (only takes effect if its row was committed).
            await session.rollback()
            await redis.delete(lock_key)
            try:
                await session.execute(
                    text(
                        "UPDATE jobs SET status = 'failed', error = 'enqueue_failed',"
                        " updated_at = NOW() WHERE id = :id"
                    ),
                    {"id": new_job_id},
                )
                await session.commit()
            except Exception:
                await session.rollback()
            raise

        return {"job_id": new_job_id, "deduped": False}
    finally:
        await redis.aclose()
