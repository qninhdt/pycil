"""Word-generation worker transitions the durable Pycil job exactly once."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pycil_worker.jobs import generate_word


def _entry(word: str, sense_id: int):
    return SimpleNamespace(
        word_id=9,
        display=word,
        norm=word,
        status="ready",
        entry_type="word",
        senses=[SimpleNamespace(sense_id=sense_id)],
    )


def _context(reader, worker_engine):
    @asynccontextmanager
    async def session_factory():
        yield object()

    return {
        "session_factory": session_factory,
        "lexi_reader": reader,
        "lexi_engine": worker_engine,
    }


async def _resolved(value):
    """Await-able stand-in for a service call whose arguments are not asserted."""
    return value


async def test_generate_word_task_publishes_sse_snapshot_result(monkeypatch):
    import fakeredis.aioredis

    task_id = uuid4()
    owner_id = uuid4()
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    class Reader:
        async def search(self, _query):
            return []

    class WorkerEngine:
        async def generate_fenced(self, source):
            assert source == "term"
            return _entry("term", 44)

    task = SimpleNamespace(id=task_id, lease_token="lease-token", lease_fence=1)
    transitions = []

    async def claim_task(_session, seen_task_id, _worker_id):
        assert seen_task_id == task_id
        return task

    async def transition_task(_session, seen_task_id, **kwargs):
        transitions.append((seen_task_id, kwargs))
        return object()

    monkeypatch.setattr(generate_word.task_service, "claim_task", claim_task)
    monkeypatch.setattr(generate_word.task_service, "transition_task", transition_task)

    ctx = _context(Reader(), WorkerEngine()) | {"redis": redis}
    result = await generate_word.generate_word_task(ctx, str(task_id), "term", str(owner_id))

    assert result == {"status": "succeeded", "wordId": 9, "senseIds": [44]}
    assert transitions[0][1]["result"] == {"wordId": 9, "senseIds": [44]}
    await redis.flushall()


async def test_generate_word_task_releases_the_inflight_slot_it_was_charged(monkeypatch):
    """The enqueued job must return the inflight slot the submitter charged.

    Both producers reserve two inflight counters bounded by
    `word_generation_max_inflight_per_user` (10), and this job is the only place
    that can return them. Once it released neither, ten successful generations
    exhausted a learner's budget until the 900s TTL lapsed, and the eleventh was
    refused with 429 while nothing was in flight.

    Driven through a Lua-capable fake Redis and asserted on the counter rather than
    on a call count, because the counter is what bounds the next request.
    """
    import fakeredis.aioredis
    from pycil.content.application import generation_quota

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    owner_id, task_id = uuid4(), uuid4()
    assert await generation_quota.reserve_quota(redis, owner_id) is True
    user_key = f"word-generation:inflight:user:{owner_id}"
    assert await redis.get(user_key) == "1"

    class Reader:
        async def search(self, _query):
            return []

    class WorkerEngine:
        async def generate_fenced(self, _source):
            return _entry("term", 44)

    task = SimpleNamespace(id=task_id, lease_token="lease-token", lease_fence=1)

    async def claim_task(_session, _seen_task_id, _worker_id):
        return task

    async def transition_task(_session, _seen_task_id, **_kwargs):
        return task

    monkeypatch.setattr(generate_word.task_service, "claim_task", claim_task)
    monkeypatch.setattr(generate_word.task_service, "transition_task", transition_task)

    ctx = _context(Reader(), WorkerEngine()) | {"redis": redis}
    result = await generate_word.generate_word_task(ctx, str(task_id), "term", str(owner_id))

    assert result["status"] == "succeeded"
    assert await redis.get(user_key) is None, (
        "generate_word_task must release the inflight slot the route charged"
    )
    assert await redis.get("word-generation:inflight:global") is None
    await redis.flushall()


async def test_generate_word_task_releases_the_slot_on_the_failure_path(monkeypatch):
    """The failure path leaks the same slot, and it is the one most likely recharged.

    A failed generation is precisely what a learner retries, so a slot held here is
    charged again seconds later.
    """
    import fakeredis.aioredis
    from pycil.content.application import generation_quota

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    owner_id, task_id = uuid4(), uuid4()
    assert await generation_quota.reserve_quota(redis, owner_id) is True
    user_key = f"word-generation:inflight:user:{owner_id}"

    class Reader:
        async def search(self, _query):
            raise RuntimeError("lexi unavailable")

    task = SimpleNamespace(id=task_id, lease_token="lease-token", lease_fence=1)
    monkeypatch.setattr(
        generate_word.task_service, "claim_task", lambda *_a: _resolved(task)
    )
    monkeypatch.setattr(
        generate_word.task_service, "transition_task", lambda *_a, **_k: _resolved(task)
    )

    ctx = _context(Reader(), object()) | {"redis": redis}
    result = await generate_word.generate_word_task(ctx, str(task_id), "term", str(owner_id))

    assert result["status"] == "failed"
    assert await redis.get(user_key) is None, (
        "a failed generation must not keep holding the inflight slot"
    )
    await redis.flushall()


async def test_generate_word_task_keeps_the_slot_when_its_lease_was_reclaimed(monkeypatch):
    """A stale worker must not release a slot another attempt now owns.

    `transition_task` returns None when the lease token or fence no longer matches,
    which is exactly the case where a second worker has taken over. Releasing here
    would free a slot that the live attempt is still charged for, letting a learner
    exceed the inflight bound — the mirror image of the leak.
    """
    import fakeredis.aioredis
    from pycil.content.application import generation_quota

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    owner_id, task_id = uuid4(), uuid4()
    assert await generation_quota.reserve_quota(redis, owner_id) is True
    user_key = f"word-generation:inflight:user:{owner_id}"

    class Reader:
        async def search(self, _query):
            return []

    class WorkerEngine:
        async def generate_fenced(self, _source):
            return _entry("term", 44)

    task = SimpleNamespace(id=task_id, lease_token="lease-token", lease_fence=1)
    monkeypatch.setattr(
        generate_word.task_service, "claim_task", lambda *_a: _resolved(task)
    )
    # The fenced transition rejects this worker: another attempt owns the task.
    monkeypatch.setattr(
        generate_word.task_service, "transition_task", lambda *_a, **_k: _resolved(None)
    )

    ctx = _context(Reader(), WorkerEngine()) | {"redis": redis}
    result = await generate_word.generate_word_task(ctx, str(task_id), "term", str(owner_id))

    assert result == {"status": "stale"}
    assert await redis.get(user_key) == "1", (
        "a stale worker must leave the live attempt's slot charged"
    )
    await redis.flushall()


async def test_generate_word_task_refuses_a_call_with_no_owner(monkeypatch):
    """The owner is required, so a caller that omits it fails at the call.

    This used to assert the opposite: that a three-argument call settled the task
    anyway, as tolerance for jobs queued by a previous release during a rolling
    deploy. No such job has ever been queued. What the default actually bought was
    a caller who could forget the argument and leak the learner's inflight slot
    until the 900s TTL lapsed, with nothing failing.
    """
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    task_id = uuid4()

    class Reader:
        async def search(self, _query):
            return []

    class WorkerEngine:
        async def generate_fenced(self, _source):
            return _entry("term", 44)

    ctx = _context(Reader(), WorkerEngine()) | {"redis": redis}
    with pytest.raises(TypeError):
        await generate_word.generate_word_task(ctx, str(task_id), "term")
    await redis.flushall()


async def test_the_task_path_logs_the_cause_it_discards(monkeypatch, caplog):
    """The failure branch swallows the provider exception and records only a code.

    `transition_task` stores `word_generation_failed` and nothing else, so the
    exception is the only account of *why* and it ends here. That gap was found the
    hard way: an E2E generation failed, the log said only that the job returned
    `failed`, and the cause had to be reproduced inside the container by hand.
    """
    import logging

    task_id, owner_id = uuid4(), uuid4()

    class Reader:
        async def search(self, _query):
            raise RuntimeError("the provider returned an empty payload")

    recorded: dict[str, object] = {}

    async def transition(_session, _task_id, **kwargs):
        recorded["error_code"] = kwargs.get("error_code")
        return SimpleNamespace(id=task_id)

    task = SimpleNamespace(id=task_id, lease_token="lease-token", lease_fence=1)
    monkeypatch.setattr(
        generate_word.task_service, "claim_task", lambda *_a: _resolved(task)
    )
    monkeypatch.setattr(generate_word.task_service, "transition_task", transition)

    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    ctx = _context(Reader(), object()) | {"redis": redis}
    with caplog.at_level(logging.ERROR, logger=generate_word.logger.name):
        result = await generate_word.generate_word_task(
            ctx, str(task_id), "truculent", str(owner_id)
        )

    assert result["status"] == "failed"
    assert recorded["error_code"] == "word_generation_failed"
    # The traceback, not just the fact. A record without `exc_info` leaves the
    # operator exactly where the E2E failure left me.
    assert any(
        record.exc_info is not None and "truculent" in record.getMessage()
        for record in caplog.records
    ), f"the cause was not logged; records: {[r.getMessage() for r in caplog.records]}"
    await redis.flushall()
