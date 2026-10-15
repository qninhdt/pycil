"""Bounded process-local objects and optional typed Redis values."""

from math import isfinite

from cachetools import TTLCache
from pydantic import TypeAdapter, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from pycil.infrastructure.observability import get_logger

logger = get_logger(__name__)


class MemoryCache[K, V]:
    def __init__(self, max_entries: int, ttl: float) -> None:
        if (
            type(max_entries) is not int
            or max_entries <= 0
            or type(ttl) not in (int, float)
            or not isfinite(ttl)
            or ttl <= 0
        ):
            raise ValueError("Cache capacity and TTL must be positive")
        self.values = TTLCache[K, V, float](maxsize=max_entries, ttl=ttl)

    def get(self, key: K) -> V | None:
        return self.values.get(key)

    def put(self, key: K, value: V) -> None:
        self.values[key] = value

    def discard(self, key: K) -> None:
        self.values.pop(key, None)

    def clear(self) -> None:
        self.values.clear()


class RedisCache[T]:
    def __init__(self, redis: Redis, model: type[T], prefix: str, ttl: int) -> None:
        if type(ttl) is not int or ttl <= 0 or not prefix:
            raise ValueError("Cache prefix and positive integer TTL are required")
        self.redis = redis
        self.adapter = TypeAdapter(model)
        self.prefix = prefix
        self.ttl = ttl

    async def get(self, key: str) -> T | None:
        try:
            payload = await self.redis.get(f"{self.prefix}:{key}")
            return None if payload is None else self.adapter.validate_json(payload)
        except RedisError, ValidationError:
            logger.warning("cache_read_failed", cache_prefix=self.prefix)
            return None

    async def put(self, key: str, value: T) -> None:
        payload = self.adapter.dump_json(value, warnings="error")
        try:
            await self.redis.set(f"{self.prefix}:{key}", payload, ex=self.ttl)
        except RedisError:
            logger.warning("cache_write_failed", cache_prefix=self.prefix)

    async def discard(self, key: str) -> None:
        try:
            await self.redis.delete(f"{self.prefix}:{key}")
        except RedisError:
            logger.warning("cache_invalidation_failed", cache_prefix=self.prefix)
