"""Word-generation worker transitions the durable Pycil job exactly once."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

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


async def test_generate_word_persists_terminal_result_and_publishes(monkeypatch):
    job_id = uuid4()
    calls: list[tuple[str, object]] = []
    events: list[tuple] = []

    class Reader:
        async def search(self, query):
            assert query == "serendipity"
            return [SimpleNamespace(display="serendipity", entry_type="word")]

    class WorkerEngine:
        async def generate_fenced(self, source):
            assert source.display == "serendipity"
            return _entry("serendipity", 44)

    async def claim_generation(_session, seen_job_id, worker_id, **_kwargs):
        calls.append(("running", seen_job_id))
        assert worker_id == "worker-a"
        return SimpleNamespace(id=job_id, lease_token="lease-token", lease_fence=1)

    async def complete_generation(_session, seen_job_id, token, fence, result):
        assert (token, fence) == ("lease-token", 1)
        calls.append(("succeeded", (seen_job_id, result)))
        return SimpleNamespace(owner_id=uuid4())

    async def release_inflight_quota(_redis, _owner_id):
        return None

    async def publish(*args, **kwargs):
        events.append((args, kwargs))

    from pycil.jobs import service as jobs_service

    monkeypatch.setattr(jobs_service, "claim_generation", claim_generation)
    monkeypatch.setattr(jobs_service, "complete_generation", complete_generation)
    monkeypatch.setattr(jobs_service, "release_inflight_quota", release_inflight_quota)
    monkeypatch.setattr(generate_word.realtime, "publish_job", publish)

    result = await generate_word.generate_word(
        _context(Reader(), WorkerEngine()) | {"worker_id": "worker-a", "redis": object()},
        "owner",
        "serendipity",
        str(job_id),
    )

    assert result == {"status": "succeeded", "wordId": 9, "senseIds": [44]}
    assert calls == [
        ("running", job_id),
        ("succeeded", (job_id, {"wordId": 9, "senseIds": [44]})),
    ]
    assert events[0][0] == ("owner", str(job_id), "running")
    assert events[1][0] == ("owner", str(job_id), "succeeded")
    assert events[1][1] == {"detail": "serendipity"}


async def test_generate_word_ignores_retried_job(monkeypatch):
    job_id = uuid4()

    async def claim_generation(_session, _seen_job_id, _worker_id, **_kwargs):
        return None

    from pycil.jobs import service as jobs_service

    monkeypatch.setattr(jobs_service, "claim_generation", claim_generation)
    result = await generate_word.generate_word(
        _context(object(), object()), "owner", "term", str(job_id)
    )
    assert result == {"status": "duplicate"}


async def test_generate_word_task_publishes_sse_snapshot_result(monkeypatch):
    task_id = uuid4()

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

    result = await generate_word.generate_word_task(
        _context(Reader(), WorkerEngine()), str(task_id), "term"
    )

    assert result == {"status": "succeeded", "wordId": 9, "senseIds": [44]}
    assert transitions[0][1]["result"] == {"wordId": 9, "senseIds": [44]}


async def test_generate_word_schedules_retry_instead_of_arq_redelivery(monkeypatch):
    job_id = uuid4()
    events = []

    class Reader:
        async def search(self, _query):
            raise RuntimeError("lexi unavailable")

    async def claim_generation(_session, _seen_job_id, _worker_id, **_kwargs):
        return SimpleNamespace(lease_token="lease-token", lease_fence=1)

    async def fail_generation(_session, _seen_job_id, token, fence, code):
        assert (token, fence, code) == ("lease-token", 1, "generation_failed")
        return SimpleNamespace(status=SimpleNamespace(value="queued"))

    async def publish(*args, **kwargs):
        events.append((args, kwargs))

    from pycil.jobs import service as jobs_service

    monkeypatch.setattr(jobs_service, "claim_generation", claim_generation)
    monkeypatch.setattr(jobs_service, "fail_generation", fail_generation)
    monkeypatch.setattr(generate_word.realtime, "publish_job", publish)
    result = await generate_word.generate_word(
        _context(Reader(), object()), "owner", "term", str(job_id)
    )
    assert result == {"status": "retry_scheduled"}
    assert events[-1][0] == ("owner", str(job_id), "queued")


async def test_generate_word_returns_stale_when_failure_lease_was_reclaimed(monkeypatch):
    job_id = uuid4()

    class Reader:
        async def search(self, _query):
            raise RuntimeError("lexi unavailable")

    async def claim_generation(_session, _seen_job_id, _worker_id, **_kwargs):
        return SimpleNamespace(lease_token="lease-token", lease_fence=1)

    async def fail_generation(*_args):
        return None

    from pycil.jobs import service as jobs_service

    monkeypatch.setattr(jobs_service, "claim_generation", claim_generation)
    monkeypatch.setattr(jobs_service, "fail_generation", fail_generation)
    result = await generate_word.generate_word(
        _context(Reader(), object()), "owner", "term", str(job_id)
    )
    assert result == {"status": "stale"}


async def test_generate_word_task_releases_the_inflight_slot_it_was_charged(monkeypatch):
    """B1: the enqueued job must return the inflight slot the route charged.

    `POST /word-generations` reserves two inflight counters bounded by
    `word_generation_max_inflight_per_user` (10). The legacy `generate_word` handler
    releases them on its terminal paths; `generate_word_task` — the job the route
    actually enqueues — released neither. Ten successful generations therefore
    exhausted a learner's budget until the 900s TTL lapsed, and the eleventh was
    refused with 429 while nothing was in flight.

    Driven through a Lua-capable fake Redis and asserted on the counter rather than
    on a call count, because the counter is what bounds the next request.
    """
    import fakeredis.aioredis
    from pycil.jobs import service as jobs_service

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    owner_id, task_id = uuid4(), uuid4()
    assert await jobs_service.reserve_quota(redis, owner_id) is True
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
    from pycil.jobs import service as jobs_service

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    owner_id, task_id = uuid4(), uuid4()
    assert await jobs_service.reserve_quota(redis, owner_id) is True
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
    from pycil.jobs import service as jobs_service

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    owner_id, task_id = uuid4(), uuid4()
    assert await jobs_service.reserve_quota(redis, owner_id) is True
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


async def test_generate_word_task_without_an_owner_settles_without_releasing(monkeypatch):
    """An in-flight job enqueued by the previous release carries no owner.

    The argument is optional so that a rolling deploy — new worker, jobs already
    queued by the old API — settles the task instead of raising TypeError. Such a
    job cannot release a slot it cannot attribute, and the 900s TTL remains the
    backstop for that window only.
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

    task = SimpleNamespace(id=task_id, lease_token="lease-token", lease_fence=1)
    monkeypatch.setattr(
        generate_word.task_service, "claim_task", lambda *_a: _resolved(task)
    )
    monkeypatch.setattr(
        generate_word.task_service, "transition_task", lambda *_a, **_k: _resolved(task)
    )

    ctx = _context(Reader(), WorkerEngine()) | {"redis": redis}
    result = await generate_word.generate_word_task(ctx, str(task_id), "term")
    assert result == {"status": "succeeded", "wordId": 9, "senseIds": [44]}
    await redis.flushall()


async def test_a_failed_generation_logs_the_cause_it_discards(monkeypatch, caplog):
    """The failure path records a code and drops the exception; it must log first.

    `fail_generation` stores `generation_failed` and nothing else, so a swallowed
    exception left no evidence anywhere of *why* a word failed to generate. A live
    failure had to be diagnosed by reproducing the call inside the container by
    hand — the worker log said only that the job returned `failed`.

    Asserted on the log record rather than on the return value, because the return
    value was never the problem.
    """
    import logging

    from pycil.jobs import service as jobs_service

    class ExplodingReader:
        async def search(self, query):
            raise RuntimeError("the provider returned an empty payload")

    recorded: dict[str, object] = {}

    async def claim_generation(_session, _job_id, _worker_id, **_kwargs):
        return SimpleNamespace(lease_token="token", lease_fence=1, owner_id=uuid4())

    async def fail_generation(_session, _job_id, _token, _fence, code):
        recorded["code"] = code
        return SimpleNamespace(status="failed", owner_id=uuid4())

    monkeypatch.setattr(jobs_service, "claim_generation", claim_generation)
    monkeypatch.setattr(jobs_service, "fail_generation", fail_generation)
    monkeypatch.setattr(
        jobs_service, "release_inflight_quota", lambda *a, **k: _resolved(None)
    )
    monkeypatch.setattr(
        generate_word.realtime, "publish_job", lambda *a, **k: _resolved(None)
    )

    # `_context` predates the quota release, which reads ctx["redis"].
    context = _context(ExplodingReader(), object()) | {"redis": object()}
    with caplog.at_level(logging.ERROR, logger=generate_word.logger.name):
        result = await generate_word.generate_word(
            context, str(uuid4()), "truculent", str(uuid4())
        )

    assert result["status"] == "failed"
    assert recorded["code"] == "generation_failed"
    # The cause, not just the fact. A record with no traceback would leave the
    # operator exactly where they were.
    assert any(
        record.exc_info is not None and "truculent" in record.getMessage()
        for record in caplog.records
    ), f"the cause was not logged; records: {[r.getMessage() for r in caplog.records]}"
