"""Shared worker test fixtures.

The worker's tests split by what they actually exercise: `tests/unit` covers pure
handler decisions with no infrastructure, and `tests/integration` covers the
broker, Redis and Lexi boundaries against real or faithful stand-ins.

Redis is a fake in-process server rather than a container: these tests assert the
broker's command usage and the receipt's transitions, which are Redis semantics
fakeredis implements, and requiring a container for them would make the unit-ish
part of the suite unrunnable without Docker.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def fake_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis]:
    """A disposable Redis with Lua support, so `eval`-based scripts work."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
