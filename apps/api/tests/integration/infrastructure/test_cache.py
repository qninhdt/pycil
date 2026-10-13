from pydantic import BaseModel

from pycil.infrastructure.cache import RedisCache


async def test_typed_cache_expiry_invalidation_and_corrupt_values(redis_store):
    class Profile(BaseModel):
        name: str

    redis, namespace = redis_store
    cache = RedisCache(redis, namespace)
    value = Profile(name="Learner")
    await cache.put("profile", value, 60)
    assert await cache.get("profile", Profile) == value
    assert 0 < await redis.ttl(cache.key("profile")) <= 60
    await cache.discard("profile")
    assert await cache.get("profile", Profile) is None

    for payload in (b"invalid JSON", b'{"name": null}', b"\xff"):
        await redis.set(cache.key("profile"), payload)
        assert await cache.get("profile", Profile) is None
    await redis.delete(cache.key("profile"))
    await redis.lpush(cache.key("profile"), "wrong Redis type")
    assert await cache.get("profile", Profile) is None
    await cache.discard("profile")
    await cache.put("profile", value, 60)
    assert await cache.get("profile", Profile) == value


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
    cache = RedisCache(rejected, namespace)
    try:
        with capture_logs() as logs:
            assert await cache.get("profile", Profile) is None
            await cache.put("profile", Profile(name="private profile data"), 60)
            await cache.discard("profile")
        assert [record["event"] for record in logs] == [
            "cache_read_failed",
            "cache_write_failed",
            "cache_invalidation_failed",
        ]
        assert "private profile data" not in str(logs)
        assert "invalid-test-only" not in str(logs)
        assert not await redis.exists(cache.key("profile"))
    finally:
        await rejected.aclose()
