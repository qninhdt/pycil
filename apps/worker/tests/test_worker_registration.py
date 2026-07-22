"""Worker registration is importable without Redis/PostgreSQL services."""

import asyncio

from pycil_worker import main
from pycil_worker.main import WorkerSettings


def test_pending_grade_reconciliation_is_registered():
    assert {function.__name__ for function in WorkerSettings.functions} >= {
        "generate_word",
        "generate_question",
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
