"""Short execution leases; a pending approval holds no slot."""

from dataclasses import dataclass
from uuid import UUID, uuid7

from redis.asyncio import Redis

from pycil.billing.plans import PlanKey, get_plan
from pycil.platform.settings import settings

SLOTS = max(get_plan(plan).assistant_concurrency for plan in PlanKey)
STARTS_PER_MINUTE = 10

_ACQUIRE = """
if redis.call('exists', KEYS[1]) == 1 then return 0 end
local limit = tonumber(ARGV[2])
if limit == 1 then
  for i = 2, #KEYS do
    if redis.call('exists', KEYS[i]) == 1 then return 0 end
  end
end
for i = 2, limit + 1 do
  if redis.call('exists', KEYS[i]) == 0 then
    redis.call('psetex', KEYS[1], ARGV[3], ARGV[1])
    redis.call('psetex', KEYS[i], ARGV[3], ARGV[1])
    return i - 1
  end
end
return 0
"""

_RENEW = """
if redis.call('get', KEYS[1]) ~= ARGV[1] or redis.call('get', KEYS[2]) ~= ARGV[1] then
  return 0
end
redis.call('pexpire', KEYS[1], tonumber(ARGV[2]))
redis.call('pexpire', KEYS[2], tonumber(ARGV[2]))
return 1
"""

_RELEASE = """
local released = 0
for i = 1, #KEYS do
  if redis.call('get', KEYS[i]) == ARGV[1] then
    released = released + redis.call('del', KEYS[i])
  end
end
return released
"""

_RATE = """
local count = redis.call('incr', KEYS[1])
if count == 1 then redis.call('expire', KEYS[1], 60) end
return {count, redis.call('ttl', KEYS[1])}
"""


@dataclass(frozen=True)
class TurnLease:
    user_id: UUID
    thread_id: UUID
    slot: int
    token: str


def lease_ttl_seconds() -> int:
    return settings.assistant_run_deadline_seconds + 30


def thread_lease_key(thread_id: UUID) -> str:
    return f"assistant:running:{thread_id}"


def _slot_key(user_id: UUID, slot: int) -> str:
    return f"assistant:slot:{user_id}:{slot}"


def _keys(user_id: UUID, thread_id: UUID) -> list[str]:
    return [thread_lease_key(thread_id), *(_slot_key(user_id, i) for i in range(SLOTS))]


async def acquire_turn_lease(
    redis: Redis, user_id: UUID, thread_id: UUID, plan: PlanKey
) -> TurnLease | None:
    token = uuid7().hex
    limit = get_plan(plan).assistant_concurrency
    slot = int(
        await redis.eval(
            _ACQUIRE,
            SLOTS + 1,
            *_keys(user_id, thread_id),
            token,
            limit,
            lease_ttl_seconds() * 1000,
        )
    )
    return TurnLease(user_id, thread_id, slot - 1, token) if slot else None


async def renew_turn_lease(redis: Redis, lease: TurnLease) -> bool:
    return bool(
        await redis.eval(
            _RENEW,
            2,
            thread_lease_key(lease.thread_id),
            _slot_key(lease.user_id, lease.slot),
            lease.token,
            lease_ttl_seconds() * 1000,
        )
    )


async def release_turn_lease(redis: Redis, lease: TurnLease) -> bool:
    return bool(
        await redis.eval(
            _RELEASE,
            2,
            thread_lease_key(lease.thread_id),
            _slot_key(lease.user_id, lease.slot),
            lease.token,
        )
    )


async def check_start_rate(redis: Redis, user_id: UUID) -> int | None:
    count, retry_after = await redis.eval(_RATE, 1, f"assistant:starts:{user_id}")
    return max(1, int(retry_after)) if int(count) > STARTS_PER_MINUTE else None
