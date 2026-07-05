"""Answer flow: verdict from lexi only, FSRS update, first-attempt-only, tamper-proof."""

from datetime import UTC, datetime

import pytest
from lexi_ai.read_models import Question, Score
from sqlalchemy import select

from pycil.auth.models import User
from pycil.common.errors import NotFoundError
from pycil.learning import service
from pycil.learning.models import ReviewLog, UserSenseStats

pytestmark = pytest.mark.asyncio


class FakeLexiClient:
    """Fake port: serves an authoritative question by id + a canned verdict.

    Records the (question, answer) it was asked to grade so a test can prove the
    server graded the RE-FETCHED question, not any client-supplied payload.
    """

    def __init__(self, question: Question, correct: bool = True):
        self._question = question
        self._correct = correct
        self.graded: list[tuple[Question, object]] = []

    async def get_question(self, question_id: int):
        if question_id != self._question.id:
            return None
        return self._question

    async def grade(self, question, answer):
        self.graded.append((question, answer))
        return Score(correct=self._correct, score=1.0 if self._correct else 0.0, kind="rule")

    async def search(self, q):  # pragma: no cover - unused here
        return []

    async def generate(self, s):  # pragma: no cover
        ...

    async def get_senses(self, ids):  # pragma: no cover
        return []

    async def generate_questions(self, e, formats, n):  # pragma: no cover
        return []


def _q(qid=1, sense_id=42) -> Question:
    return Question(
        id=qid, word_id=7, sense_id=sense_id, format="definition_mcq",
        answer_kind="choice", payload={"prompt": "?", "options": ["a", "b"], "answer": 0},
    )


async def _user(session, email="learner@x.co") -> User:
    u = User(email=email)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


async def test_first_answer_creates_stats_and_review_log(session):
    user = await _user(session)
    client = FakeLexiClient(_q(sense_id=42), correct=True)
    out = await service.answer(
        session, client, user.id, question_id=1, raw_answer="0",
        session_id="s1", now=datetime.now(UTC), seen_senses=set(),
    )
    assert out.is_correct
    assert out.mastery_after >= 0
    assert out.first_attempt

    stats = (await session.execute(
        select(UserSenseStats).where(UserSenseStats.sense_id == 42)
    )).scalars().first()
    assert stats is not None and stats.review_count == 1
    logs = (await session.execute(select(ReviewLog))).scalars().all()
    assert len(logs) == 1


async def test_grades_refetched_question_not_client_payload(session):
    user = await _user(session)
    q = _q(qid=1, sense_id=42)
    client = FakeLexiClient(q, correct=True)
    await service.answer(
        session, client, user.id, question_id=1, raw_answer="my-answer",
        session_id="s1", now=datetime.now(UTC), seen_senses=set(),
    )
    # The graded question is the server's authoritative object, by identity.
    assert client.graded[0][0] is q
    assert client.graded[0][1] == "my-answer"


async def test_unknown_question_id_404(session):
    user = await _user(session)
    client = FakeLexiClient(_q(qid=1), correct=True)
    with pytest.raises(NotFoundError):
        await service.answer(
            session, client, user.id, question_id=999, raw_answer="x",
            session_id="s1", now=datetime.now(UTC), seen_senses=set(),
        )


async def test_second_attempt_same_sense_does_not_move_stability(session):
    user = await _user(session)
    client = FakeLexiClient(_q(sense_id=42), correct=True)
    now = datetime.now(UTC)
    seen: set[int] = set()
    first = await service.answer(
        session, client, user.id, 1, "0", "s1", now, seen,
    )
    s_after_first = first.stability_after
    # Second attempt on the SAME sense in the same session: relearning, no S move.
    second = await service.answer(
        session, client, user.id, 1, "0", "s1", now, seen,
    )
    assert not second.first_attempt
    assert second.stability_after == s_after_first
    # review_log has exactly one row (only the first attempt logged).
    logs = (await session.execute(select(ReviewLog))).scalars().all()
    assert len(logs) == 1


async def test_wrong_answer_records_lapse(session):
    user = await _user(session)
    client = FakeLexiClient(_q(sense_id=99), correct=False)
    out = await service.answer(
        session, client, user.id, 1, "wrong", "s1", datetime.now(UTC), set(),
    )
    assert not out.is_correct
    stats = (await session.execute(
        select(UserSenseStats).where(UserSenseStats.sense_id == 99)
    )).scalars().first()
    assert stats.lapse_count == 1
