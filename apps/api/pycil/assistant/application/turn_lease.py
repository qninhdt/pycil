"""One active assistant turn per learner.

This bounds how much a single learner can overspend in parallel: two turns would
both pass the positive-balance admission gate, and each is allowed to finish even
if its debit drives the balance negative, so together they could exceed the
allowance by more than one turn's worth.

The lease is a resource bound, not a billing record. PostgreSQL's unique
``(kind, reference_id)`` ledger key stays the correctness boundary, so a Redis
outage costs at most a little parallel overspend rather than a wrong balance.
"""

from redis.asyncio import Redis

from pycil.config import settings
from pycil.db.redis import acquire_lease, release_lease, renew_lease

TURN_LEASE_PREFIX = "assistant:turn:"


def turn_lease_key(user_id) -> str:
    return f"{TURN_LEASE_PREFIX}{user_id}"


def lease_ttl_seconds() -> int:
    """Outlive the turn deadline so the lease cannot expire mid-turn.

    A lease that expired while the turn still ran would admit a second turn, which
    is exactly what it exists to prevent. It is still bounded, so a crashed
    process cannot leave a learner locked out permanently.
    """
    return settings.assistant_run_deadline_seconds + 30


def pending_lease_ttl_seconds() -> int:
    """Bound a paused approval run by the thread retention window."""
    return max(1, settings.assistant_retention_days) * 24 * 60 * 60


async def acquire_turn_lease(redis: Redis, user_id) -> str | None:
    """Return the lease token, or ``None`` when a turn is already active."""
    return await acquire_lease(redis, turn_lease_key(user_id), lease_ttl_seconds())


async def release_turn_lease(redis: Redis, user_id, token: str) -> bool:
    """Release the lease if this request still owns it."""
    return await release_lease(redis, turn_lease_key(user_id), token)


async def renew_turn_lease(
    redis: Redis, user_id, token: str, *, ttl_seconds: int | None = None
) -> bool:
    """Extend the active turn while preserving the owner-token guard."""
    return await renew_lease(
        redis,
        turn_lease_key(user_id),
        token,
        lease_ttl_seconds() if ttl_seconds is None else ttl_seconds,
    )
