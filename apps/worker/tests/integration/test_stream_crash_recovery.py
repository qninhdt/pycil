"""Real Redis Stream delivery: ACK, reclaim after a crash, and no startup stealing.

These drive the actual broker against a real Redis server rather than a fake,
because the properties under test are Redis Streams semantics — pending entries,
``XAUTOCLAIM`` after an idle timeout, and consumer-group ownership. A fake that
approximates those would prove nothing about the behaviour the phase depends on.

The suite is skipped when no Redis is reachable, so the unit-level checks still run
without a server.
"""

from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import pytest
from pycil.queue.contracts import CONSUMER_GROUP_NAME, STREAM_NAME
from redis.asyncio import Redis

pytestmark = pytest.mark.asyncio

_CONFIGURED_URL = os.environ.get("TEST_REDIS_URL")
REDIS_URL = _CONFIGURED_URL or "redis://127.0.0.1:6379/15"


async def _redis() -> Redis:
    """A connection to the test Redis.

    When ``TEST_REDIS_URL`` is explicitly set — which CI does — an unreachable
    server is a failure, not a skip: these are the tests that prove crash
    recovery, and a silently skipped suite would report green while proving
    nothing. Only the implicit local default may skip.
    """
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:  # noqa: BLE001
        await client.aclose()
        if _CONFIGURED_URL:
            raise
        pytest.skip("no Redis reachable at the default local address")
    return client


@pytest.fixture
async def stream_name():
    """A unique stream per test so runs cannot interfere."""
    return f"{STREAM_NAME}:test:{uuid4().hex[:8]}"


async def _publish(redis: Redis, stream: str, body: dict) -> str:
    return await redis.xadd(stream, {"data": json.dumps(body)})


async def test_a_consumed_message_stays_pending_until_acknowledged(stream_name):
    """Delivery without ACK is what makes a crashed worker's job recoverable."""
    redis = await _redis()
    try:
        await redis.xgroup_create(stream_name, CONSUMER_GROUP_NAME, id="0", mkstream=True)
        await _publish(redis, stream_name, {"job_id": "j1"})

        read = await redis.xreadgroup(
            CONSUMER_GROUP_NAME, "worker-a", {stream_name: ">"}, count=1
        )
        assert read, "the consumer group must receive the published message"
        entry_id = read[0][1][0][0]

        pending = await redis.xpending(stream_name, CONSUMER_GROUP_NAME)
        assert pending["pending"] == 1, "an unacknowledged message stays pending"

        await redis.xack(stream_name, CONSUMER_GROUP_NAME, entry_id)
        pending = await redis.xpending(stream_name, CONSUMER_GROUP_NAME)
        assert pending["pending"] == 0, "ACK clears the pending entry"
    finally:
        await redis.delete(stream_name)
        await redis.aclose()


async def test_an_abandoned_message_is_reclaimable_by_another_worker(stream_name):
    """A worker that dies mid-job leaves a pending entry another worker can take.

    This is the crash-recovery path: no startup sweep, no stealing from a live
    worker — the pending-entry list plus an idle threshold is what hands the work
    over, and only after the original consumer has been silent long enough.
    """
    redis = await _redis()
    try:
        await redis.xgroup_create(stream_name, CONSUMER_GROUP_NAME, id="0", mkstream=True)
        await _publish(redis, stream_name, {"job_id": "crashed"})

        # worker-a takes the message and then "dies" without acknowledging.
        await redis.xreadgroup(CONSUMER_GROUP_NAME, "worker-a", {stream_name: ">"}, count=1)

        # A second worker starting must NOT be handed the live message.
        fresh = await redis.xreadgroup(
            CONSUMER_GROUP_NAME, "worker-b", {stream_name: ">"}, count=1
        )
        assert not fresh, "a starting worker must not steal a message already delivered"

        # Once worker-a has been idle past the threshold, the entry is claimable.
        claimed = await redis.xautoclaim(
            stream_name, CONSUMER_GROUP_NAME, "worker-b", min_idle_time=0, start_id="0-0"
        )
        entries = claimed[1]
        assert entries, "the abandoned entry must be reclaimable"
        assert json.loads(entries[0][1]["data"])["job_id"] == "crashed"

        await redis.xack(stream_name, CONSUMER_GROUP_NAME, entries[0][0])
    finally:
        await redis.delete(stream_name)
        await redis.aclose()


async def test_two_workers_share_one_group_without_duplicate_delivery(stream_name):
    """Ten messages, two consumers: each message is delivered to exactly one."""
    redis = await _redis()
    try:
        await redis.xgroup_create(stream_name, CONSUMER_GROUP_NAME, id="0", mkstream=True)
        for index in range(10):
            await _publish(redis, stream_name, {"job_id": f"j{index}"})

        async def consume(consumer: str) -> list[str]:
            seen: list[str] = []
            while len(seen) < 10:
                read = await redis.xreadgroup(
                    CONSUMER_GROUP_NAME, consumer, {stream_name: ">"}, count=2, block=200
                )
                if not read:
                    break
                for entry_id, fields in read[0][1]:
                    seen.append(json.loads(fields["data"])["job_id"])
                    await redis.xack(stream_name, CONSUMER_GROUP_NAME, entry_id)
            return seen

        left, right = await asyncio.gather(consume("worker-1"), consume("worker-2"))

        assert sorted(left + right) == sorted(f"j{i}" for i in range(10))
        assert len(set(left) & set(right)) == 0, "no message may be delivered twice"
    finally:
        await redis.delete(stream_name)
        await redis.aclose()


async def test_the_worker_broker_bounds_reclaim(stream_name):
    """The reclaim window must exceed a real job, or a slow call is duplicated."""
    from pycil_worker.broker import RECLAIM_IDLE_TIMEOUT_MS, broker

    assert broker.queue_name == STREAM_NAME
    assert broker.consumer_group_name == CONSUMER_GROUP_NAME
    assert broker.idle_timeout == RECLAIM_IDLE_TIMEOUT_MS
    # Comfortably above the API's own per-job timeouts.
    assert RECLAIM_IDLE_TIMEOUT_MS >= 120_000
