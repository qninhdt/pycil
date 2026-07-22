"""Durable task-outbox relay acknowledgement and retry behavior."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from pycil_worker.jobs import dispatch_task_outbox


def _context():
    @asynccontextmanager
    async def session_factory():
        yield object()

    return {"worker_id": "worker-a", "session_factory": session_factory}


async def test_dispatch_acknowledges_only_after_centrifugo_accepts(monkeypatch):
    row = SimpleNamespace(id=uuid4(), channel="async:task", payload={"eventId": "event"})
    calls = []

    async def claim(_session, owner):
        assert owner == "worker-a:task-outbox"
        return [row]

    async def acknowledge(_session, row_id, owner):
        calls.append((row_id, owner))
        return row

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {}

    class Client:
        async def post(self, *_args, **_kwargs):
            return Response()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(dispatch_task_outbox.service, "claim_outbox_batch", claim)
    monkeypatch.setattr(dispatch_task_outbox.service, "acknowledge_outbox", acknowledge)
    monkeypatch.setattr(dispatch_task_outbox.httpx, "AsyncClient", lambda **_kwargs: Client())

    assert await dispatch_task_outbox.dispatch_task_outbox(_context()) == {
        "published": 1,
        "retried": 0,
        "deadLetters": 0,
    }
    assert calls == [(row.id, "worker-a:task-outbox")]


async def test_dispatch_retries_when_centrifugo_rejects(monkeypatch):
    row = SimpleNamespace(id=uuid4(), channel="async:task", payload={"eventId": "event"})
    retries = []

    async def claim(_session, _owner):
        return [row]

    async def retry(_session, row_id, owner):
        retries.append((row_id, owner))
        return SimpleNamespace(status=SimpleNamespace(value="pending"))

    class Client:
        async def post(self, *_args, **_kwargs):
            raise dispatch_task_outbox.httpx.ConnectError("unavailable")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(dispatch_task_outbox.service, "claim_outbox_batch", claim)
    monkeypatch.setattr(dispatch_task_outbox.service, "retry_outbox", retry)
    monkeypatch.setattr(dispatch_task_outbox.httpx, "AsyncClient", lambda **_kwargs: Client())

    assert await dispatch_task_outbox.dispatch_task_outbox(_context()) == {
        "published": 0,
        "retried": 1,
        "deadLetters": 0,
    }
    assert retries == [(row.id, "worker-a:task-outbox")]


async def test_dispatch_logs_dead_letter_for_operational_alerting(monkeypatch):
    row = SimpleNamespace(id=uuid4(), channel="async:task", payload={"eventId": "event"})
    logs = []

    async def claim(_session, _owner):
        return [row]

    async def retry(_session, _row_id, _owner):
        return SimpleNamespace(status=SimpleNamespace(value="dead_letter"))

    class Client:
        async def post(self, *_args, **_kwargs):
            raise dispatch_task_outbox.httpx.ConnectError("unavailable")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(dispatch_task_outbox.service, "claim_outbox_batch", claim)
    monkeypatch.setattr(dispatch_task_outbox.service, "retry_outbox", retry)
    monkeypatch.setattr(dispatch_task_outbox.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(
        dispatch_task_outbox.logger, "error", lambda *args, **kwargs: logs.append(args)
    )

    assert await dispatch_task_outbox.dispatch_task_outbox(_context()) == {
        "published": 0,
        "retried": 0,
        "deadLetters": 1,
    }
    assert logs == [("async task outbox delivery exhausted",)]
