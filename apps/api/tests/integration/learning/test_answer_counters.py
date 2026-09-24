"""apply_answer maintains review/lapse counters and one review-log row per grade.

`review_count` and `lapse_count` are durable counters on the learner-sense row and
are surfaced to the client (``reviewCount``/``lapseCount``). Because one sense is
graded at most once per session (`B9`), a counter only advances when the same sense
is reviewed again in a *later* session, which is the path exercised here — the
established-sense branch that a single-session flow test never reaches.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from pycil.auth.models import User
from pycil.learning import service
from pycil.learning.models import Response, ReviewLog
from pycil.policy.sense_state import SenseStatus, UserSenseStats

pytestmark = pytest.mark.asyncio


async def _grade(session, redis, *, user_id, sense_id, session_id, verdict, now):
    """Persist one graded answer through the real two-axis write."""
    response = Response(
        user_id=user_id,
        session_id=session_id,
        sense_id=sense_id,
        question_id=1,
        requested_level=1,
        served_level=1,
        idempotency_key=f"{session_id}:{sense_id}",
    )
    session.add(response)
    await session.flush()
    return await service.apply_answer(
        session,
        redis,
        response=response,
        verdict=verdict,
        score=None,
        feedback=None,
        now=now,
        delivery_round=0,
        render_format="mcq",
    )


async def _stats(session, user_id, sense_id) -> UserSenseStats:
    row = await session.scalar(
        select(UserSenseStats).where(
            UserSenseStats.user_id == user_id, UserSenseStats.sense_id == sense_id
        )
    )
    assert row is not None
    await session.refresh(row)  # reload the committed row rather than trust the cache
    return row


async def test_counters_advance_each_session_and_one_log_row_per_grade(session, fake_redis):
    user = User(email="answer-counter@example.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    user_id = user.id  # capture before any later reload expires the instance
    sense_id = 7
    base = datetime(2026, 1, 1, tzinfo=UTC)

    # First grade: a new sense enters scheduling at depth 1 with one review, no lapse.
    await _grade(
        session, fake_redis, user_id=user_id, sense_id=sense_id,
        session_id="s1", verdict=True, now=base,
    )
    first = await _stats(session, user_id, sense_id)
    assert first.status == SenseStatus.scheduled
    assert first.depth_level == 1
    assert (first.review_count, first.lapse_count) == (1, 0)

    # A later session, wrong: the review counts again and the lapse is recorded —
    # the established branch that previously left both frozen at their entry values.
    await _grade(
        session, fake_redis, user_id=user_id, sense_id=sense_id,
        session_id="s2", verdict=False, now=base + timedelta(days=1),
    )
    second = await _stats(session, user_id, sense_id)
    assert (second.review_count, second.lapse_count) == (2, 1)

    # A third session, correct: the review counts, the lapse total holds.
    await _grade(
        session, fake_redis, user_id=user_id, sense_id=sense_id,
        session_id="s3", verdict=True, now=base + timedelta(days=2),
    )
    third = await _stats(session, user_id, sense_id)
    assert (third.review_count, third.lapse_count) == (3, 1)

    # Exactly one review-log row per graded answer (`B9`).
    log_rows = await session.scalar(
        select(func.count(ReviewLog.id)).where(
            ReviewLog.user_id == user_id, ReviewLog.sense_id == sense_id
        )
    )
    assert log_rows == 3
