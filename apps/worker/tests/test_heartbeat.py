"""API readiness has a bounded, worker-owned liveness signal."""

from shared.tasks.contract import WORKER_HEARTBEAT_KEY, WORKER_HEARTBEAT_TTL_SECONDS

from pycil_worker.jobs.heartbeat import heartbeat


async def test_heartbeat_sets_short_lived_redis_key():
    calls = []

    class Redis:
        async def setex(self, *args):
            calls.append(args)

    assert await heartbeat({"redis": Redis()}) == {"status": "ok"}
    assert calls == [(WORKER_HEARTBEAT_KEY, WORKER_HEARTBEAT_TTL_SECONDS, "1")]
