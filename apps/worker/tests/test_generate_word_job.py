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

        async def generate(self, source):
            assert source.display == "serendipity"
            return Entry(
                word_id=9,
                display="serendipity",
                norm="serendipity",
                status="ready",
                entry_type="word",
                senses=[SenseView("luck", "core", None, None, sense_id=44)],
            )

    async def mark_running(_session, seen_job_id):
        calls.append(("running", seen_job_id))
        return SimpleNamespace()

    async def mark_succeeded(_session, seen_job_id, result):
        calls.append(("succeeded", (seen_job_id, result)))
        return SimpleNamespace()

    async def publish(*args, **kwargs):
        events.append((args, kwargs))

    from pycil.jobs import service as jobs_service

    monkeypatch.setattr(jobs_service, "mark_running", mark_running)
    monkeypatch.setattr(jobs_service, "mark_succeeded", mark_succeeded)
    monkeypatch.setattr(generate_word.realtime, "publish_job", publish)

    result = await generate_word.generate_word(
        _context(Client()), "owner", "serendipity", str(job_id)
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

    async def mark_running(_session, _seen_job_id):
        return None

    from pycil.jobs import service as jobs_service

    monkeypatch.setattr(jobs_service, "mark_running", mark_running)
    result = await generate_word.generate_word(
        _context(object()), "owner", "term", str(job_id)
    )
    assert result == {"status": "duplicate"}
