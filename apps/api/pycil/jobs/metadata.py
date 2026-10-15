"""Only ownership and expiry live here; Taskiq stores results and progress."""

from uuid import UUID

from redis.asyncio import Redis


def owner_key(job_id: str) -> str:
    return f"pycil:jobs:owner:{job_id}"


async def owned(redis: Redis, job_id: str, user: UUID) -> bool:
    return await redis.get(owner_key(job_id)) == str(user).encode()
