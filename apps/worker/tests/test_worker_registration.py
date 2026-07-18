"""Worker registration is importable without Redis/PostgreSQL services."""

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
        "reconcile_expired_assistant_actions",
        "reconcile_assistant_retention",
    }
    assert WorkerSettings.cron_jobs
