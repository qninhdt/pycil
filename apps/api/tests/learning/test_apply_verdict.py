"""apply_verdict: idempotent async-grade resolution (no LLM double-bill on retry)."""

from datetime import UTC, datetime

import pytest
from lexi_ai.read_models import Question, Score
from sqlalchemy import select

from pycil.auth.models import User
from pycil.learning import service
from pycil.learning.models import GradeStatus, Response, ReviewLog

pytestmark = pytest.mark.asyncio


class CountingLexiClient:
    """Counts grade() calls so a test can prove a retry does NOT re-grade."""

    def __init__(self, question: Question, correct: bool = True):
        self._question = question
        self._correct = correct
        self.grade_calls = 0

    async def get_question(self, question_id: int):
        return self._question if question_id == self._question.id else None

    async def grade(self, question, answer):
        self.grade_calls += 1
        return Score(correct=self._correct, score=1.0 if self._correct else 0.0, kind="llm")


def _q(qid=1, sense_id=42) -> Question:
    return Question(
        id=qid, word_id=7, sense_id=sense_id, format="use_in_sentence",
        answer_kind="text", payload={"prompt": "use it"},
    )


async def _seed_pending(session, user_id, sense_id=42, question_id=1, answer="my sentence"):
    resp = Response(
        user_id=user_id,
        sense_id=sense_id,
        question_id=str(question_id),
        grade_status=GradeStatus.pending,
        grade_feedback=answer,  # WRITE answer parked here until async grade
    )
    session.add(resp)
    await session.commit()
    await session.refresh(resp)
    return resp


async def _user(session) -> User:
    u = User(email="writer@x.co")
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def test_apply_verdict_resolves_pending(session):
    user = await _user(session)
    resp = await _seed_pending(session, user.id)
    client = CountingLexiClient(_q(), correct=True)

    out = await service.apply_verdict(session, client, resp.id, datetime.now(UTC))
    assert out is not None and out.is_correct
    assert client.grade_calls == 1

    await session.refresh(resp)
    assert resp.grade_status == GradeStatus.graded
    logs = (await session.execute(select(ReviewLog))).scalars().all()
    assert len(logs) == 1


async def test_apply_verdict_retry_is_noop(session):
    """A retried grade job (arq max_tries=2) must NOT re-grade or re-bill."""
    user = await _user(session)
    resp = await _seed_pending(session, user.id)
    client = CountingLexiClient(_q(), correct=True)

    first = await service.apply_verdict(session, client, resp.id, datetime.now(UTC))
    assert first is not None
    assert client.grade_calls == 1

    # Retry the SAME response — already terminal → no-op, no second grade call.
    second = await service.apply_verdict(session, client, resp.id, datetime.now(UTC))
    assert second is None
    assert client.grade_calls == 1  # NOT re-billed

    logs = (await session.execute(select(ReviewLog))).scalars().all()
    assert len(logs) == 1  # only one FSRS update applied
