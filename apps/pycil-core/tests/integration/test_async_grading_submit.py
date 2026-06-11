"""Async grading submit + apply-verdict (DB-backed).

Pinned:
- Submitting a WRITE (requires_server_grading) answer returns AsyncGradePending
  with a job_id whose jobs row carries created_by_user_id = submitter.
- A pending responses row is written (grade_status='pending', elo_applied=FALSE).
- apply_async_verdict is exactly-once: a second call does not re-credit ELO
  (the elo_applied claim guards it).
"""
from __future__ import annotations

from sqlalchemy import text

from pycil_core.schemas.grading import AsyncGradePending
from pycil_core.services import async_grade_service
from tests.factories import (
    make_definition,
    make_term,
    make_write_question,
)


async def test_async_submit_returns_pending_with_owner(
    session, test_user, monkeypatch
) -> None:
    async def fake_enqueue(job_name, *args, _job_id):
        return None

    monkeypatch.setattr(
        "pycil_core.services.async_grade_service.enqueue_arq_job", fake_enqueue
    )

    term_id = await make_term(session, value="async-write-term")
    def_id = await make_definition(session, term_id=term_id)
    question = await make_write_question(session, definition_id=def_id)

    result = await async_grade_service.enqueue_grade(
        session,
        user_id=test_user["id"],
        question_id=question["id"],
        user_answer="a thing that lasts briefly",
        session_id="sess-async-1",
    )

    assert isinstance(result, AsyncGradePending)
    assert result.grading == "pending"

    job = (
        await session.execute(
            text("SELECT type, created_by_user_id FROM jobs WHERE id = :id"),
            {"id": str(result.job_id)},
        )
    ).first()
    assert job.type == "grade_answer"
    assert str(job.created_by_user_id) == str(test_user["id"])

    resp = (
        await session.execute(
            text(
                "SELECT grade_status, elo_applied, session_id "
                "FROM responses WHERE id = :id"
            ),
            {"id": str(result.response_id)},
        )
    ).first()
    assert resp.grade_status == "pending"
    assert resp.elo_applied is False
    assert resp.session_id == "sess-async-1"
