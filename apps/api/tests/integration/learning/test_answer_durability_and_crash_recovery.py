"""A graded answer is durable at submit time, and no failure can regrade it.

The phase's central claim is that every graded answer commits its Response, FSRS
strength and depth to PostgreSQL immediately, so Redis loss can end a live session
but cannot erase learning. These drive the real submit path and assert exact row
counts, because "the response looks right" would pass even if the durable write had
not happened.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from lexi_ai.contracts import Evaluation, PresentedQuestion, RenderKind
from sqlalchemy import func, select

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ServiceUnavailableError
from pycil.hierarchy.domain.vocabulary import NodeType
from pycil.hierarchy.infra.models import Node
from pycil.learning import answering, service, session_store
from pycil.learning.models import Response, ReviewLog
from pycil.policy.sense_state import UserSenseStats

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


async def _user(session, email: str = "durable@example.test") -> User:
    user = User(email=email, clerk_id=f"user_{email}")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _question(sense_id: int = 41, level: int = 1) -> PresentedQuestion:
    return PresentedQuestion(
        question_id=7,
        type_id=1,
        interaction="assessment",
        render_kind=RenderKind.SINGLE_CHOICE,
        difficulty_level=level,
        render={"stem": "What does it mean?", "options": ["a", "b"]},
        sense_id=sense_id,
        word_id=1,
    )


class _Reader:
    """A Lexi reader that returns a fixed question and a fixed verdict."""

    def __init__(self, *, correct: bool = True, raise_on_evaluate: Exception | None = None):
        self.correct = correct
        self.raise_on_evaluate = raise_on_evaluate
        self.evaluate_calls = 0

    async def get_question(self, question_id: int) -> PresentedQuestion:
        return _question()

    async def evaluate_answer(self, question_id: int, submission) -> Evaluation:
        self.evaluate_calls += 1
        if self.raise_on_evaluate is not None:
            raise self.raise_on_evaluate
        return Evaluation(
            question_id=question_id,
            status="graded",
            correct=self.correct,
            score=1.0,
            feedback="ok",
        )


async def _counts(session) -> tuple[int, int, int]:
    responses = await session.scalar(select(func.count()).select_from(Response))
    reviews = await session.scalar(select(func.count()).select_from(ReviewLog))
    stats = await session.scalar(select(func.count()).select_from(UserSenseStats))
    return int(responses), int(reviews), int(stats)


async def _grade_once(session, redis, reader, user, *, sense_id: int = 41):
    """One graded write through the durable two-axis path."""
    response = Response(
        user_id=user.id,
        session_id="sess-1",
        sense_id=sense_id,
        question_id=7,
        requested_level=1,
        served_level=1,
        idempotency_key=f"sess-1:{sense_id}",
    )
    session.add(response)
    await session.flush()
    return await service.apply_answer(
        session,
        redis,
        response=response,
        verdict=True,
        score=1.0,
        feedback="ok",
        now=NOW,
        delivery_round=0,
        render_format="mcq",
    )


async def test_one_graded_answer_writes_exactly_one_durable_row_set(session, fake_redis):
    user = await _user(session)
    outcome = await _grade_once(session, fake_redis, None, user)

    responses, reviews, stats = await _counts(session)
    assert (responses, reviews, stats) == (1, 1, 1)
    assert outcome.response_id is not None


async def test_a_duplicate_submit_cannot_write_a_second_learning_effect(session, fake_redis):
    """The unique key is what makes a network retry safe.

    The same (user, session, sense) is one graded assessment. A retry that reached
    the database twice must not produce a second Response, a second ReviewLog or a
    second FSRS application.
    """
    from sqlalchemy.exc import IntegrityError

    user = await _user(session, "duplicate@example.test")
    await _grade_once(session, fake_redis, None, user)
    before = await _counts(session)

    # The retry builds the same row; the unique constraint is the guard.
    duplicate = Response(
        user_id=user.id,
        session_id="sess-1",
        sense_id=41,
        question_id=7,
        requested_level=1,
        served_level=1,
        idempotency_key="sess-1:41",
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()

    assert await _counts(session) == before


async def test_committed_learning_survives_losing_the_session_document(session, fake_redis):
    """Redis loss may end a live session; it cannot erase a graded answer.

    The document is deleted outright after the commit, and the learner's state is
    read back from PostgreSQL — which is the whole reason canonical strength and
    depth are not stored in Redis.
    """
    user = await _user(session, "redis-loss@example.test")
    outcome = await _grade_once(session, fake_redis, None, user)

    await fake_redis.flushall()  # the session document is gone

    response = await session.get(Response, outcome.response_id)
    assert response is not None, "the committed response must survive Redis loss"
    row = await session.scalar(
        select(UserSenseStats).where(
            UserSenseStats.user_id == user.id, UserSenseStats.sense_id == 41
        )
    )
    assert row is not None
    await session.refresh(row)
    assert row.stability > 0, "FSRS strength is durable, not session state"
    assert row.depth_level >= 0, "depth is a durable column, not session state"


async def test_a_wrong_answer_moves_strength_down_and_keeps_the_response(session, fake_redis):
    """The failure path must still be durable — it is the one that schedules a re-ask."""
    user = await _user(session, "wrong@example.test")
    response = Response(
        user_id=user.id,
        session_id="sess-2",
        sense_id=42,
        question_id=7,
        requested_level=1,
        served_level=1,
        idempotency_key="sess-2:42",
    )
    session.add(response)
    await session.flush()
    await service.apply_answer(
        session,
        fake_redis,
        response=response,
        verdict=False,
        score=0.0,
        feedback="not quite",
        now=NOW,
        delivery_round=0,
        render_format="mcq",
    )

    row = await session.scalar(
        select(UserSenseStats).where(
            UserSenseStats.user_id == user.id, UserSenseStats.sense_id == 42
        )
    )
    await session.refresh(row)
    assert row.lapse_count == 1, "a wrong answer is recorded as a lapse"
    responses, reviews, _ = await _counts(session)
    assert (responses, reviews) == (1, 1)


async def test_a_provider_failure_leaves_no_durable_trace(session, fake_redis):
    """A failed evaluation must not look like a learner error.

    The phase is explicit that a provider timeout leaves the item answerable and
    produces no false grade, no FSRS effect and no charge.
    """
    user = await _user(session, "provider-down@example.test")
    reader = _Reader(raise_on_evaluate=ServiceUnavailableError("free_text_grade_unavailable"))

    # The delivery must exist for submit to accept the question.
    await session_store.create(
        fake_redis,
        "sess-3",
        owner_id=user.id,
        node_id=user.id,
        scope_generation=1,
        target_words=5,
        max_per_round=5,
        admitted=[session_store.AdmittedSense(sense_id=41, purpose="new", requested_level=1)],
    )
    await session_store.set_delivered(
        fake_redis, "sess-3", 41, 7, kind="grade", round_index=0
    )

    with pytest.raises(ServiceUnavailableError):
        await answering.submit(
            session,
            fake_redis,
            reader,
            user=CurrentUser(id=user.id, email=user.email),
            session_id="sess-3",
            question_id=7,
            answer="something",
            now=NOW,
        )

    responses, reviews, stats = await _counts(session)
    assert (responses, reviews, stats) == (0, 0, 0), (
        "a provider failure must leave no Response, ReviewLog or learner-state row"
    )
    delivery = await session_store.get_delivery(fake_redis, "sess-3", 41)
    assert delivery is not None and delivery.question_id == 7


async def test_retry_repairs_a_committed_answer_after_redis_projection_crash(
    session, fake_redis, monkeypatch
):
    """A retry after commit returns the saved verdict and repairs Redis without regrading."""
    user = await _user(session, "projection-crash@example.test")
    node = Node(author_id=user.id, type=NodeType.DECK, name="Crash recovery")
    session.add(node)
    await session.commit()
    await session.refresh(node)
    current_user = CurrentUser(id=user.id, email=user.email)
    reader = _Reader()
    await session_store.create(
        fake_redis,
        "sess-crash",
        owner_id=user.id,
        node_id=node.id,
        scope_generation=1,
        target_words=5,
        max_per_round=5,
        admitted=[session_store.AdmittedSense(41, "new", 1)],
    )
    await session_store.set_delivered(
        fake_redis, "sess-crash", 41, 7, kind="grade", round_index=0
    )

    project = session_store.apply_grade_projection

    async def crash_after_database_commit(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(
        session_store, "apply_grade_projection", crash_after_database_commit
    )
    with pytest.raises(asyncio.CancelledError):
        await answering.submit(
            session,
            fake_redis,
            reader,
            user=current_user,
            session_id="sess-crash",
            question_id=7,
            answer="answer",
            now=NOW,
        )

    assert await _counts(session) == (1, 1, 1)
    monkeypatch.setattr(session_store, "apply_grade_projection", project)

    async def question_was_removed(question_id: int):
        return None

    monkeypatch.setattr(reader, "get_question", question_was_removed)
    outcome = await answering.submit(
        session,
        fake_redis,
        reader,
        user=current_user,
        session_id="sess-crash",
        question_id=7,
        answer="answer",
        now=NOW,
    )
    assert outcome.response_id is not None
    assert reader.evaluate_calls == 1
    assert await session_store.is_graded(fake_redis, "sess-crash", 41)
    assert await _counts(session) == (1, 1, 1)

    duplicate = await answering.submit(
        session,
        fake_redis,
        reader,
        user=current_user,
        session_id="sess-crash",
        question_id=7,
        answer="different retry payload",
        now=NOW,
    )
    assert duplicate.response_id == outcome.response_id
    assert reader.evaluate_calls == 1
