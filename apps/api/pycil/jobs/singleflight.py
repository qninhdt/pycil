"""Reuse an owned in-flight job while serializing matching submissions."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from redis.asyncio import Redis
from taskiq import AsyncBroker

from pycil.jobs.metadata import owned


@asynccontextmanager
async def singleflight(
    redis: Redis, broker: AsyncBroker, key: str, user: UUID
) -> AsyncGenerator[str | None]:
    async with redis.lock(
        key + ":lock",
        timeout=30,
        blocking_timeout=5,
        thread_local=False,
        raise_on_release_error=False,
    ):
        existing: str | None = None
        if value := await redis.get(key):
            job_id = value.decode() if isinstance(value, bytes) else str(value)
            if await owned(redis, job_id, user) and not await broker.result_backend.is_result_ready(
                job_id
            ):
                existing = job_id
        yield existing
