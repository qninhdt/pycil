"""Worker registration is importable without Redis/PostgreSQL services."""

from pycil_worker.main import WorkerSettings


def test_pending_grade_reconciliation_is_registered():
    assert {function.__name__ for function in WorkerSettings.functions} >= {
        "generate_word",
        "generate_question",
        "grade_answer",
        "grade_answer_v1",
        "reconcile_pending_grades",
    }
    assert WorkerSettings.cron_jobs
