"""Per-user LLM spend cap (P6 phase 1).

Reads spend from `openrouter:spend:{user_id}:{YYYY-MM-DD}` Redis counter
that worker increments via `add_spend(redis, user_id, cost)`. Default cap
is per-user $1/day; override via env / users.daily_llm_cap_usd column when
that lands.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis


DEFAULT_PER_USER_DAILY_USD = 1.0
USER_SPEND_KEY_PREFIX = "openrouter:spend"


def _user_spend_key(user_id: UUID) -> str:
    return f"{USER_SPEND_KEY_PREFIX}:{user_id}:{date.today().isoformat()}"


async def get_user_spend_today(redis: Redis, user_id: UUID) -> float:
    raw = await redis.get(_user_spend_key(user_id))
    if not raw:
        return 0.0
    return float(raw if not isinstance(raw, bytes) else raw.decode())


async def assert_under_user_cap(
    redis: Redis,
    user_id: UUID,
    *,
    projected_cost_usd: float,
    cap_usd: float = DEFAULT_PER_USER_DAILY_USD,
) -> None:
    """Reject jobs that would push the user past their daily cap."""
    spent = await get_user_spend_today(redis, user_id)
    if spent + projected_cost_usd > cap_usd:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED, "user_daily_llm_cap_exceeded"
        )


async def record_user_spend(redis: Redis, user_id: UUID, cost_usd: float) -> float:
    """Increment per-user counter and bump TTL. Worker mirror calls this."""
    key = _user_spend_key(user_id)
    new_val = await redis.incrbyfloat(key, cost_usd)
    await redis.expire(key, 60 * 60 * 25)
    return float(new_val)
