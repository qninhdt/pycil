"""The word-generation budget: per-hour, per-day, and inflight ceilings.

The budget is charged before a task is submitted and released when the work
settles or never starts. It is independent of how the work itself is tracked —
both the HTTP route and the assistant tool charge the same four keys, so a
learner cannot spend twice the allowance by using two entry points.
"""

import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

_RESERVE_QUOTA = """
local limits = {tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), tonumber(ARGV[4])}
for i = 1, 4 do
  if tonumber(redis.call('GET', KEYS[i]) or '0') >= limits[i] then return 0 end
end
for i = 1, 4 do
  redis.call('INCR', KEYS[i])
  if i <= 2 then redis.call('EXPIRE', KEYS[i], tonumber(ARGV[4 + i])) end
  if i >= 3 then redis.call('EXPIRE', KEYS[i], tonumber(ARGV[7])) end
end
return 1
"""

_RELEASE_INFLIGHT = """
for i = 1, 2 do
  local value = tonumber(redis.call('GET', KEYS[i]) or '0')
  if value <= 1 then redis.call('DEL', KEYS[i]) else redis.call('DECR', KEYS[i]) end
end
return 1
"""


def _now() -> datetime:
    return datetime.now(UTC)


def _quota_keys(owner_id: UUID, now: datetime) -> tuple[str, str, str, str]:
    return (
        f"word-generation:hour:{owner_id}:{now.strftime('%Y%m%d%H')}",
        f"word-generation:day:{now.strftime('%Y%m%d')}",
        f"word-generation:inflight:user:{owner_id}",
        "word-generation:inflight:global",
    )


async def reserve_quota(redis: Redis, owner_id: UUID) -> bool:
    """Atomically charge a request and reserve its two durable inflight slots."""
    from pycil.config import settings

    now = _now()
    seconds_to_midnight = (
        int((now.replace(hour=23, minute=59, second=59, microsecond=0) - now).total_seconds()) + 1
    )
    return bool(
        await redis.eval(
            _RESERVE_QUOTA,
            4,
            *_quota_keys(owner_id, now),
            settings.word_generation_requests_per_hour,
            settings.word_generation_daily_limit,
            settings.word_generation_max_inflight_per_user,
            settings.word_generation_max_inflight_global,
            3600,
            seconds_to_midnight,
            # A worker lease lasts two minutes and retry backoff tops out at
            # two minutes; this bound prevents permanent quota leakage if a
            # process disappears before its terminal cleanup.
            900,
        )
    )


async def release_inflight_quota(redis: Redis, owner_id: UUID) -> None:
    await redis.eval(_RELEASE_INFLIGHT, 2, *_quota_keys(owner_id, _now())[2:])


def normalize_query(query: str) -> str:
    """Produce a stable lookup key without changing the submitted query."""
    return " ".join(unicodedata.normalize("NFKC", query).casefold().split())
