"""Singleflight: concurrent identical lookups share one provider generation.

The property that matters is that N simultaneous callers for an absent word cause
exactly one generation call. The other callers must join the in-flight work or read
the committed row, never start a second paid request.
"""

import asyncio

import fakeredis.aioredis
import pytest

from pycil.jobs.deduplication import singleflight_generate_word

pytestmark = pytest.mark.asyncio


async def test_concurrent_callers_share_one_generation():
    redis = fakeredis.aioredis.FakeRedis()
    calls = 0

    async def generate():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)  # stand in for provider latency
        return {"wordId": 123, "senseIds": [1, 2]}

    async def existing():
        return {"wordId": 123, "senseIds": [1, 2]}

    results = await asyncio.gather(
        *[singleflight_generate_word(redis, "serendipity", generate, existing) for _ in range(10)]
    )

    assert calls == 1, "one provider call for ten concurrent lookups"
    assert all(r == {"wordId": 123, "senseIds": [1, 2]} for r in results)


async def test_a_different_query_is_not_deduplicated():
    redis = fakeredis.aioredis.FakeRedis()
    queries: list[str] = []

    async def generate_for(query: str):
        async def generate():
            queries.append(query)
            return {"wordId": 1, "senseIds": []}

        async def existing():
            return {"wordId": 1, "senseIds": []}

        return await singleflight_generate_word(redis, query, generate, existing)

    await asyncio.gather(generate_for("alpha"), generate_for("beta"))
    assert sorted(queries) == ["alpha", "beta"]


async def test_a_failed_generation_releases_the_lease():
    """A failure must not leave a permanent lock: the next caller retries."""
    redis = fakeredis.aioredis.FakeRedis()

    async def failing():
        raise RuntimeError("provider down")

    async def existing():
        return {"wordId": 0, "senseIds": []}

    with pytest.raises(RuntimeError, match="provider down"):
        await singleflight_generate_word(redis, "retry-me", failing, existing)

    # The lease is gone, so a later caller acquires it rather than waiting.
    async def succeeding():
        return {"wordId": 9, "senseIds": [3]}

    assert await singleflight_generate_word(redis, "retry-me", succeeding, existing) == {
        "wordId": 9,
        "senseIds": [3],
    }
