from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from pycil.infrastructure.observability import get_logger

logger = get_logger(__name__)


class RedisCache:
    def __init__(self, redis: Redis, namespace: str) -> None:
        self.redis = redis
        self.namespace = namespace

    def key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    async def get[T: BaseModel](
        self,
        key: str,
        model: type[T],
    ) -> T | None:
        try:
            payload = await self.redis.get(self.key(key))
            if payload is None:
                return None

            return model.model_validate_json(payload)
        except RedisError, ValidationError:
            logger.warning("cache_read_failed", cache_key=key)
            return None

    async def put(
        self,
        key: str,
        value: BaseModel,
        ttl: int,
    ) -> None:
        if ttl <= 0:
            raise ValueError("Cache TTL must be positive")

        payload = value.model_dump_json()

        try:
            await self.redis.set(self.key(key), payload, ex=ttl)
        except RedisError:
            logger.warning("cache_write_failed", cache_key=key)

    async def discard(self, key: str) -> None:
        try:
            await self.redis.delete(self.key(key))
        except RedisError:
            logger.warning("cache_invalidation_failed", cache_key=key)
