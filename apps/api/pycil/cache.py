"""Optional detached Redis values; bounded independently of coordination keys."""

import logging

import orjson
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Expiration-ordered admission bounds keys even across multiple API processes.
# This touches only this cache namespace, never leases or rate-limit keys.
STORE = """
local now = tonumber(redis.call('TIME')[1])
-- Second-resolution scores can precede the actual expiry by a fraction of a second.
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', '(' .. now)
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[2]), KEYS[2])
local excess = redis.call('ZCARD', KEYS[1]) - tonumber(ARGV[3])
if excess > 0 then
    for _, key in ipairs(redis.call('ZRANGE', KEYS[1], 0, excess - 1)) do
        redis.call('DEL', key)
        redis.call('ZREM', KEYS[1], key)
    end
end
redis.call('EXPIRE', KEYS[1], ARGV[4])
if redis.call('ZSCORE', KEYS[1], KEYS[2]) then
    redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[2])
end
"""


class RedisCache:
    def __init__(self, redis, namespace, policy):
        self.redis = redis
        self.namespace = namespace
        self.policy = policy
        self.index = namespace + ":entries"

    def key(self, key):
        return self.namespace + ":" + key

    async def get(self, key, model):
        try:
            payload = await self.redis.get(self.key(key))
            return model.model_validate(orjson.loads(payload)) if payload is not None else None
        except RedisError, ValueError, TypeError:
            logger.warning("Optional cache read failed")
            return None

    async def put(self, key, value, ttl):
        if type(ttl) is not int:
            raise TypeError("Cache TTL must be an integer")
        index_ttl = max(self.policy.actor_ttl_seconds, self.policy.deck_ttl_seconds)
        if not 0 < ttl <= index_ttl:
            raise ValueError("Cache TTL must be between 1 and the configured maximum")
        payload = orjson.dumps(value.model_dump(mode="json"))
        if len(payload) > self.policy.max_value_bytes:
            await self.discard(key)
            return
        try:
            await self.redis.eval(
                STORE,
                2,
                self.index,
                self.key(key),
                payload,
                ttl,
                self.policy.max_entries,
                index_ttl,
            )
        except RedisError:
            logger.warning("Optional cache write failed")

    async def discard(self, key):
        try:
            async with self.redis.pipeline(transaction=True) as pipeline:
                pipeline.delete(self.key(key))
                pipeline.zrem(self.index, self.key(key))
                await pipeline.execute()
        except RedisError:
            logger.warning("Optional cache invalidation failed")
