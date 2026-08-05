"""Worker registration is importable without Redis/PostgreSQL services."""

import asyncio

import pytest
from sqlalchemy import inspect

from pycil_worker import main
from pycil_worker.main import WorkerSettings


@pytest.mark.parametrize(
    "module, model",
    [
        ("pycil.learning.models", "ReviewLog"),
        ("pycil.learning.models", "Response"),
        ("pycil.jobs.models", "WordGeneration"),
        ("pycil.tasks.models", "AsyncTask"),
    ],
)
def test_worker_startup_registers_every_referenced_table(module, model):
    """Every table a job writes can sort its foreign keys after importing the worker.

    A foreign key is not resolved when its own model is imported but when a flush
    sorts the tables, so a model whose target was never registered stays silent
    until the first write — and then only for whichever job runs first on a cold
    worker, which is why grading once failed and succeeded in the same second.
    Importing ``pycil_worker.main`` must leave every referenced table present.
    """
    imported = __import__(module, fromlist=[model])
    inspect(getattr(imported, model)).base_mapper._sorted_tables


def test_pending_grade_reconciliation_is_registered():
    assert {function.__name__ for function in WorkerSettings.functions} >= {
        "generate_word",
        "prepare_questions",
        "heartbeat",
        "grade_answer",
        "grade_answer_v1",
        "reconcile_pending_grades",
        "reconcile_queued_word_generations",
        "reconcile_async_tasks",
        "reconcile_expired_assistant_actions",
        "reconcile_assistant_retention",
    }
    assert WorkerSettings.cron_jobs


async def test_outbox_notification_coalesces_concurrent_drains(monkeypatch):
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(_ctx):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    monkeypatch.setattr(main, "dispatch_task_outbox", dispatch)
    context = {"task_outbox_drain_lock": asyncio.Lock()}
    first = asyncio.create_task(main._drain_task_outbox(context))
    await started.wait()
    await main._drain_task_outbox(context)
    release.set()
    await first

    assert calls == 1


def test_generate_word_task_accepts_the_owner_argument_as_optional():
    """Deploy-order guard for the B1 fix.

    The API now enqueues `generate_word_task` with a fourth `owner_id` argument. A
    worker that predates it raises TypeError and the job dies, so the worker must be
    deployed at or before the API. Conversely, a job already queued by the previous
    API carries only three arguments, which is why the parameter is optional rather
    than required — this asserts that direction, so a future change that makes it
    required fails here instead of stranding queued rows.
    """
    import inspect

    from pycil_worker.jobs.generate_word import generate_word_task

    parameters = inspect.signature(generate_word_task).parameters
    assert list(parameters) == ["ctx", "task_id", "query", "owner_uid"]
    assert parameters["owner_uid"].default is None, (
        "owner_uid must stay optional so jobs queued by the previous release settle"
    )
