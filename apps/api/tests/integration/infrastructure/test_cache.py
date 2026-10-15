from pydantic import BaseModel

from pycil.infrastructure.cache import RedisCache


async def test_typed_cache_expiry_invalidation_and_corrupt_values(redis_store):
    class Profile(BaseModel):
        name: str

    redis, namespace = redis_store
    cache = RedisCache(redis, Profile, namespace, 60)
    value = Profile(name="Learner")
    await cache.put("profile", value)
    assert await cache.get("profile") == value
    assert 0 < await redis.ttl(f"{namespace}:profile") <= 60
    await cache.discard("profile")
    assert await cache.get("profile") is None

    for payload in (b"invalid JSON", b'{"name": null}', b"\xff"):
        await redis.set(f"{namespace}:profile", payload)
        assert await cache.get("profile") is None
    await redis.delete(f"{namespace}:profile")
    await redis.lpush(f"{namespace}:profile", "wrong Redis type")
    assert await cache.get("profile") is None
    await cache.discard("profile")
    await cache.put("profile", value)
    assert await cache.get("profile") == value


async def test_native_redis_failure_degrades_to_cache_miss_without_publishing(
    redis_store, redis_container
):
    from redis.asyncio import Redis
    from structlog.testing import capture_logs

    class Profile(BaseModel):
        name: str

    redis, namespace = redis_store
    rejected = Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        username=namespace,
        password="invalid-test-only",
        socket_timeout=1,
        socket_connect_timeout=1,
    )
    cache = RedisCache(rejected, Profile, namespace, 60)
    try:
        with capture_logs() as logs:
            assert await cache.get("profile") is None
            await cache.put("profile", Profile(name="private profile data"))
            await cache.discard("profile")
        assert [record["event"] for record in logs] == [
            "cache_read_failed",
            "cache_write_failed",
            "cache_invalidation_failed",
        ]
        assert "private profile data" not in str(logs)
        assert "invalid-test-only" not in str(logs)
        assert not await redis.exists(f"{namespace}:profile")
    finally:
        await rejected.aclose()


async def test_uuid_instances_are_isolated_and_serialization_errors_propagate(redis_store):
    from uuid import UUID, uuid4

    import pytest
    from pydantic_core import PydanticSerializationError

    redis, namespace = redis_store
    first = RedisCache(redis, UUID, f"{namespace}:user-id:v1", 60)
    other = RedisCache(redis, UUID, f"{namespace}:other-user-id:v1", 60)
    value = uuid4()
    await first.put("clerk", value)
    assert await first.get("clerk") == value
    assert await other.get("clerk") is None
    with pytest.raises(PydanticSerializationError):
        await first.put("invalid", object())
    assert not await redis.exists(f"{namespace}:user-id:v1:invalid")
