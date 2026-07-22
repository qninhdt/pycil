"""Async tasks survive an initial ARQ enqueue outage."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from pycil_worker.jobs.reconcile_async_tasks import reconcile_async_tasks


async def test_reconciliation_reenqueues_each_task_kind(monkeypatch):
    tasks = [
        SimpleNamespace(id=uuid4(), kind="word", result={"dispatch": {"query": "run"}}),
        SimpleNamespace(
            id=uuid4(),
            kind="question_pool",
            result={"dispatch": {"word_id": 7, "formats": ["cloze"], "n": 1, "sense_id": 8}},
        ),
        SimpleNamespace(
            id=uuid4(),
            kind="grading",
            result={"dispatch": {"owner_id": "owner", "response_id": "response"}},
        ),
    ]
    enqueued = []

    @asynccontextmanager
    async def session_factory():
        yield object()

    class Redis:
        async def enqueue_job(self, *args):
            enqueued.append(args)

    from pycil.tasks import service as task_service

    async def list_reenqueueable(_session):
        return tasks

    monkeypatch.setattr(task_service, "list_reenqueueable_tasks", list_reenqueueable)

    assert await reconcile_async_tasks({"session_factory": session_factory, "redis": Redis()}) == {
        "status": "reconciled",
        "count": 3,
    }
    assert enqueued == [
        ("generate_word_task", str(tasks[0].id), "run"),
        ("generate_question", str(tasks[1].id), 7, ["cloze"], 1, None, 8),
        ("grade_answer_task", str(tasks[2].id), "owner", "response"),
    ]
