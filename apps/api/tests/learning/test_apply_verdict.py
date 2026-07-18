"""apply_verdict: idempotent async-grade resolution (no LLM double-bill on retry)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from pycil.auth.models import User
from pycil.content.lexi_types import Question, Score
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
        raw_answer=answer,
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
    assert resp.mastery_before == 0
    assert resp.mastery_after is not None and resp.mastery_after > 0
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


async def test_apply_verdict_skips_another_workers_active_lease(session):
    user = await _user(session)
    response = await _seed_pending(session, user.id)
    response.grading_lease_owner = "other-worker"
    response.grading_lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
    await session.commit()
    client = CountingLexiClient(_q(), correct=True)

    assert await service.apply_verdict(session, client, response.id, datetime.now(UTC)) is None
    assert client.grade_calls == 0


async def test_apply_verdict_times_out_before_its_five_minute_lease(session):
    """A stuck provider cannot outlive the lease and invite a second bill."""
    user = await _user(session)
    response = await _seed_pending(session, user.id)

    class SlowLexiClient(CountingLexiClient):
        async def grade(self, question, answer):
            raise TimeoutError

    with pytest.raises(TimeoutError):
        await service.apply_verdict(
            session, SlowLexiClient(_q()), response.id, datetime.now(UTC)
        )


async def test_pending_response_reuses_idempotency_key_after_lost_enqueue(session):
    user = await _user(session)
    kwargs = {
        "user_id": user.id,
        "session_id": "session-1",
        "sense_id": 42,
        "question_id": 1,
        "raw_answer": "my sentence",
        "idempotency_key": "session-1:1",
    }

    first = await service.create_pending_response(session, **kwargs)
    retry = await service.create_pending_response(session, **kwargs)

    assert retry.id == first.id
    responses = (await session.execute(select(Response))).scalars().all()
    assert len(responses) == 1
