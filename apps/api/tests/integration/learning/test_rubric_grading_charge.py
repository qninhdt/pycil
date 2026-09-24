"""Tests verifying rubric grading credit charges and unconstrained depth progression."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from lexi_ai.contracts import Evaluation, PresentedQuestion, RenderKind
from sqlalchemy import select

from pycil.account import credit
from pycil.account.models import CreditDebit
from pycil.account.plans import AccountPlan, period_grant
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError
from pycil.learning import answering, session_store
from pycil.learning.models import Response
from pycil.learning.service import apply_answer
from pycil.policy.sense_state import SenseStatus, UserSenseStats

pytestmark = pytest.mark.asyncio


class _ReaskReader:
    def __init__(self):
        self.evaluate_calls = 0

    async def get_question(self, question_id: int) -> PresentedQuestion:
        return PresentedQuestion(
            question_id=question_id,
            type_id=1,
            interaction="assessment",
            render_kind=RenderKind.FREE_TEXT,
            difficulty_level=3,
            render={"prompt": "Use the word in a sentence."},
            sense_id=104,
            word_id=1,
        )

    async def evaluate_answer(self, question_id: int, submission) -> Evaluation:
        self.evaluate_calls += 1
        return Evaluation(
            question_id=question_id,
            status="graded",
            correct=True,
            score=1.0,
            feedback="Good sentence.",
        )


async def _user(session, prefix: str = "learner") -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_rubric_grading_charges_one_credit(session, fake_redis):
    user = await _user(session)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    response = Response(
        user_id=user.id,
        session_id="test-session-rubric",
        sense_id=101,
        question_id=201,
        requested_level=3,
        served_level=3,
        render_format="free_text",
    )
    session.add(response)
    await session.commit()
    await session.refresh(response)

    initial_balance = await credit.balance(session, user.id)

    outcome = await apply_answer(
        session,
        fake_redis,
        response=response,
        verdict=True,
        score=1.0,
        feedback="Excellent sentence!",
        now=now,
        delivery_round=0,
        render_format="free_text",
    )

    assert outcome.is_correct is True
    # 1.0 Credit = 1,000 milli-credits
    new_balance = await credit.balance(session, user.id)
    assert initial_balance - new_balance == 1_000

    # Verify ledger debit entry
    debit_entry = await session.scalar(
        select(CreditDebit).where(
            CreditDebit.user_id == user.id,
            CreditDebit.reference_id == response.id,
        )
    )
    assert debit_entry is not None
    assert debit_entry.kind == "rubric_grading"
    assert debit_entry.amount == 1_000


async def test_mcq_deterministic_grading_is_free(session, fake_redis):
    user = await _user(session)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    response = Response(
        user_id=user.id,
        session_id="test-session-mcq",
        sense_id=102,
        question_id=202,
        requested_level=2,
        served_level=2,
        render_format="mcq",
    )
    session.add(response)
    await session.commit()
    await session.refresh(response)

    initial_balance = await credit.balance(session, user.id)

    outcome = await apply_answer(
        session,
        fake_redis,
        response=response,
        verdict=True,
        score=1.0,
        feedback=None,
        now=now,
        delivery_round=0,
        render_format="mcq",
    )

    assert outcome.is_correct is True
    new_balance = await credit.balance(session, user.id)
    assert new_balance == initial_balance

    # Verify NO ledger debit entry exists
    debit_entry = await session.scalar(
        select(CreditDebit).where(
            CreditDebit.user_id == user.id,
            CreditDebit.reference_id == response.id,
        )
    )
    assert debit_entry is None


async def test_depth_advances_without_withholding_when_credits_exhausted(session, fake_redis):
    user = await _user(session)
    # Drain user credits to 0
    row = await credit._ensure_credit(session, user.id)
    row.period_used = period_grant(AccountPlan.free)
    row.topup_balance = 0
    await session.commit()

    assert await credit.balance(session, user.id) == 0

    now = datetime(2030, 1, 1, tzinfo=UTC)
    # Sense already at depth 3
    stats = UserSenseStats(
        user_id=user.id,
        sense_id=103,
        status=SenseStatus.scheduled,
        review_count=5,
        stability=2.5,
        difficulty=5.0,
        last_review_date=now,
        depth_level=3,
        depth_streak=2,
    )
    session.add(stats)

    response = Response(
        user_id=user.id,
        session_id="test-session-advancement",
        sense_id=103,
        question_id=203,
        requested_level=3,
        served_level=3,
        render_format="mcq",
    )
    session.add(response)
    await session.commit()
    await session.refresh(response)

    outcome = await apply_answer(
        session,
        fake_redis,
        response=response,
        verdict=True,
        score=1.0,
        feedback=None,
        now=now,
        delivery_round=0,
        render_format="mcq",
    )

    # In the old flawed codebase, depth was withheld if credits were 0.
    # Now pedagogical progression MUST advance naturally.
    assert outcome.depth_before == 3
    assert outcome.depth_after == 4
    assert outcome.depth_after > outcome.depth_before


async def test_rubric_reask_charges_by_delivery_without_writing_learning_rows(
    session, fake_redis
):
    user = await _user(session, "reask")
    session_id = "rubric-reask-session"
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=user.id,
        node_id=uuid4(),
        scope_generation=1,
        target_words=1,
        max_per_round=1,
        admitted=[session_store.AdmittedSense(104, "due", 3)],
    )
    await session_store.apply_grade_projection(
        fake_redis,
        session_id,
        104,
        response_id=uuid4(),
        served_level=3,
        correct=False,
        failed_round=0,
    )
    await session_store.advance_round(fake_redis, session_id, expected_round=0)
    await session_store.set_delivered(
        fake_redis, session_id, 104, 204, kind="reask", round_index=1
    )
    delivery = await session_store.get_delivery(fake_redis, session_id, 104)
    assert delivery is not None and delivery.delivery_id is not None

    reader = _ReaskReader()
    outcome = await answering.submit(
        session,
        fake_redis,
        reader,
        user=CurrentUser(id=user.id, email=user.email),
        session_id=session_id,
        question_id=204,
        answer="I studied the word.",
        now=datetime.now(UTC),
    )

    assert outcome.grade_status == "ungraded"
    debit_entry = await session.scalar(
        select(CreditDebit).where(CreditDebit.reference_id == delivery.delivery_id)
    )
    assert debit_entry is not None and debit_entry.amount == 1_000
    assert await session.scalar(select(Response.id)) is None
    assert await session.scalar(select(UserSenseStats.user_id)) is None
    progress = await session_store.get_progress(fake_redis, session_id, 104)
    assert progress is not None and progress.reask_done and progress.terminal

    with pytest.raises(ConflictError, match="question_not_issued_for_session"):
        await answering.submit(
            session,
            fake_redis,
            reader,
            user=CurrentUser(id=user.id, email=user.email),
            session_id=session_id,
            question_id=204,
            answer="retry",
            now=datetime.now(UTC),
        )
    assert reader.evaluate_calls == 1
