"""Admin system-health snapshot tests (Phase 7).

- non-admin → 403.
- admin (fakeredis) → db ok, redis ok, queue_depth int.
- enqueued job reflects in queue_depth (ZCARD, not LLEN — red-team F11).
- simulated Redis failure → redis: fail, endpoint still 200 (never 500).
"""
from __future__ import annotations


def _route_redis():
    """Resolve the FakeRedis instance the admin_client installed for RedisDep."""
    from pycil_core.api.deps import RedisDep
    from pycil_core.main import app

    dep = RedisDep.__metadata__[0].dependency
    override = app.dependency_overrides.get(dep)
    assert override is not None, "admin_client must override RedisDep"
    return override()


async def test_non_admin_forbidden(client) -> None:
    assert (await client.get("/admin-api/health")).status_code == 403


async def test_admin_health_ok(admin_client) -> None:
    resp = await admin_client.get("/admin-api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["db"] == "ok"
    assert body["redis"] == "ok"
    assert isinstance(body["queue_depth"], int)


async def test_queue_depth_reflects_zset(admin_client) -> None:
    # arq stores its queue as a sorted set; seed the SAME redis the route uses
    # and confirm ZCARD is read (LLEN would WRONGTYPE → null).
    redis_obj = _route_redis()
    await redis_obj.zadd("arq:queue", {"job-1": 1.0, "job-2": 2.0})
    resp = await admin_client.get("/admin-api/health")
    assert resp.status_code == 200
    assert resp.json()["queue_depth"] == 2


async def test_redis_failure_reports_fail_not_500(admin_client, monkeypatch) -> None:
    async def boom(*a, **k):
        raise RuntimeError("redis down")

    redis_obj = _route_redis()
    monkeypatch.setattr(redis_obj, "ping", boom)

    resp = await admin_client.get("/admin-api/health")
    assert resp.status_code == 200
    assert resp.json()["redis"] == "fail"
