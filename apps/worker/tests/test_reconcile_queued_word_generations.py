"""Queued durable word jobs are recoverable after producer enqueue failure."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from pycil_worker.jobs import reconcile_queued_word_generations


async def test_reconcile_reenqueues_each_queued_generation(monkeypatch):
    records = [
        SimpleNamespace(id=uuid4(), owner_id=uuid4(), query="first"),
        SimpleNamespace(id=uuid4(), owner_id=uuid4(), query="second"),
    ]
    enqueued = []

    @asynccontextmanager
    async def session_factory():
        yield object()

    class Redis:
        async def enqueue_job(self, *args):
            enqueued.append(args)

    async def list_queued(_session):
        return records

    from pycil.jobs import service as jobs_service

    monkeypatch.setattr(jobs_service, "list_queued_generations", list_queued)
    result = await reconcile_queued_word_generations.reconcile_queued_word_generations(
        {"session_factory": session_factory, "redis": Redis()}
    )

    assert result == {"status": "reconciled", "count": 2}
    assert enqueued == [
        ("generate_word", str(record.owner_id), record.query, str(record.id))
        for record in records
    ]
