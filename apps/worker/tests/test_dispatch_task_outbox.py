"""Durable task-outbox relay acknowledgement and retry behavior."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx

from pycil_worker.jobs import dispatch_task_outbox


class _Publisher:
    """Stands in for the injected broker adapter: records and can reject."""

    def __init__(self, failure: Exception | None = None) -> None:
        self._failure = failure
        self.published: list[tuple[str, dict]] = []

    async def publish(self, channel: str, data: dict) -> None:
        self.published.append((channel, data))
        if self._failure is not None:
            raise self._failure


def _context(publisher: _Publisher):
    @asynccontextmanager
    async def session_factory():
        yield object()

    return {
        "worker_id": "worker-a",
        "session_factory": session_factory,
        "centrifugo": publisher,
    }


async def test_dispatch_acknowledges_only_after_centrifugo_accepts(monkeypatch):
    row = SimpleNamespace(id=uuid4(), channel="async:task", payload={"eventId": "event"})
    calls = []
    publisher = _Publisher()

    async def claim(_session, owner):
        assert owner == "worker-a:task-outbox"
        return [row]

    async def acknowledge(_session, row_id, owner):
        calls.append((row_id, owner))
        return row

    monkeypatch.setattr(dispatch_task_outbox.service, "claim_outbox_batch", claim)
    monkeypatch.setattr(dispatch_task_outbox.service, "acknowledge_outbox", acknowledge)

    assert await dispatch_task_outbox.dispatch_task_outbox(_context(publisher)) == {
        "published": 1,
        "retried": 0,
        "deadLetters": 0,
    }
    assert publisher.published == [("async:task", {"eventId": "event"})]
    assert calls == [(row.id, "worker-a:task-outbox")]


async def test_dispatch_retries_when_centrifugo_is_unreachable(monkeypatch):
    row = SimpleNamespace(id=uuid4(), channel="async:task", payload={"eventId": "event"})
    retries = []
    publisher = _Publisher(failure=httpx.ConnectError("unavailable"))

    async def claim(_session, _owner):
        return [row]

    async def retry(_session, row_id, owner):
        retries.append((row_id, owner))
        return SimpleNamespace(status=SimpleNamespace(value="pending"))

    monkeypatch.setattr(dispatch_task_outbox.service, "claim_outbox_batch", claim)
    monkeypatch.setattr(dispatch_task_outbox.service, "retry_outbox", retry)

    assert await dispatch_task_outbox.dispatch_task_outbox(_context(publisher)) == {
        "published": 0,
        "retried": 1,
        "deadLetters": 0,
    }
    assert retries == [(row.id, "worker-a:task-outbox")]


async def test_dispatch_retries_on_a_command_level_error_inside_a_200(monkeypatch):
    """Centrifugo reports command errors inside successful HTTP responses.

    The adapter turns that into `RuntimeError`; the relay must treat it like any
    other rejection rather than acknowledge a message the broker never accepted.
    """
    row = SimpleNamespace(id=uuid4(), channel="async:task", payload={"eventId": "event"})
    retried = []
    acknowledged = []
    publisher = _Publisher(failure=RuntimeError("centrifugo_command_rejected"))

    async def claim(_session, _owner):
        return [row]

    async def retry(_session, row_id, owner):
        retried.append((row_id, owner))
        return SimpleNamespace(status=SimpleNamespace(value="pending"))

    async def acknowledge(_session, _row_id, _owner):
        acknowledged.append(True)
        return None

    monkeypatch.setattr(dispatch_task_outbox.service, "claim_outbox_batch", claim)
    monkeypatch.setattr(dispatch_task_outbox.service, "retry_outbox", retry)
    monkeypatch.setattr(dispatch_task_outbox.service, "acknowledge_outbox", acknowledge)

    assert await dispatch_task_outbox.dispatch_task_outbox(_context(publisher)) == {
        "published": 0,
        "retried": 1,
        "deadLetters": 0,
    }
    assert retried == [(row.id, "worker-a:task-outbox")]
    assert acknowledged == []


async def test_dispatch_logs_dead_letter_for_operational_alerting(monkeypatch):
    row = SimpleNamespace(id=uuid4(), channel="async:task", payload={"eventId": "event"})
    logs = []
    publisher = _Publisher(failure=httpx.ConnectError("unavailable"))

    async def claim(_session, _owner):
        return [row]

    async def retry(_session, _row_id, _owner):
        return SimpleNamespace(status=SimpleNamespace(value="dead_letter"))

    monkeypatch.setattr(dispatch_task_outbox.service, "claim_outbox_batch", claim)
    monkeypatch.setattr(dispatch_task_outbox.service, "retry_outbox", retry)
    monkeypatch.setattr(
        dispatch_task_outbox.logger, "error", lambda *args, **kwargs: logs.append(args)
    )

    assert await dispatch_task_outbox.dispatch_task_outbox(_context(publisher)) == {
        "published": 0,
        "retried": 0,
        "deadLetters": 1,
    }
    assert logs == [("async task outbox delivery exhausted",)]
