"""Word-generation worker transitions the durable Pycil job exactly once."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from pycil.content.lexi_types import Entry, SearchResult, SenseView

from pycil_worker.jobs import generate_word


def _context(client):
    @asynccontextmanager
    async def session_factory():
        yield object()

    return {"session_factory": session_factory, "lexi_client": client}


async def test_generate_word_persists_terminal_result_and_publishes(monkeypatch):
    job_id = uuid4()
    calls: list[tuple[str, object]] = []
    events: list[tuple] = []

    class Client:
        async def search(self, query):
            assert query == "serendipity"
            return [SearchResult(display="serendipity", entry_type="word")]

        async def generate(self, source, *, idempotency_key=None):
            assert source.display == "serendipity"
            assert idempotency_key == f"pycil-generation-{job_id}"
            return Entry(
                word_id=9,
                display="serendipity",
                norm="serendipity",
                status="ready",
                entry_type="word",
                senses=[SenseView("luck", "core", None, None, sense_id=44)],
            )

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
        _context(Client()) | {"worker_id": "worker-a", "redis": object()},
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
    result = await generate_word.generate_word(_context(object()), "owner", "term", str(job_id))
    assert result == {"status": "duplicate"}


async def test_generate_word_schedules_retry_instead_of_arq_redelivery(monkeypatch):
    job_id = uuid4()
    events = []

    class Client:
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
    result = await generate_word.generate_word(_context(Client()), "owner", "term", str(job_id))
    assert result == {"status": "retry_scheduled"}
    assert events[-1][0] == ("owner", str(job_id), "queued")
