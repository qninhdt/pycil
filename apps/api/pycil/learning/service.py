"""Learning service: the FSRS-backed answer flow.

The verdict comes ENTIRELY from lexi-ai — the server re-fetches the authoritative
question by id (never trusts a client-supplied payload), grades via the port,
then applies the FSRS update under a per-(user,sense) row lock so a concurrent
double-answer applies exactly one first-attempt stability update.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from shared.fsrs import mastery as mastery_of
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import NotFoundError
from pycil.content.lexi_port import LexiClient
from pycil.learning import grading
from pycil.learning.fsrs_wrapper import first_review, next_state
from pycil.learning.models import GradeStatus, Response, ReviewLog, SenseStatus, UserSenseStats


@dataclass
class AnswerOutcome:
    sense_id: int
    is_correct: bool
    grade_score: float
    grade_feedback: str | None
    mastery_before: int
    mastery_after: int
    stability_after: float
    first_attempt: bool


async def answer(
    session: AsyncSession,
    client: LexiClient,
    user_id: UUID,
    question_id: int,
    raw_answer: str,
    session_id: str,
    now: datetime,
    seen_senses: set[int],
) -> AnswerOutcome:
    """Grade an answer and update memory state atomically.

    ``seen_senses`` tracks first-attempt-per-sense within the study session: only
    the first attempt mutates stability; re-drills are relearning steps.
    """
    # 1. Re-fetch the AUTHORITATIVE question server-side — never trust the client.
    question = await client.get_question(question_id)
    if question is None:
        raise NotFoundError("question_not_found")
    if question.sense_id is None:
        raise NotFoundError("question_has_no_sense")
    sense_id = question.sense_id

    # 2. Verdict comes entirely from lexi — pycil does no grading.
    score = await client.grade(question, raw_answer)
    correct = score.correct
    grade = grading.fsrs_grade(score)

    first_attempt = sense_id not in seen_senses

    # 3. Per-(user,sense) row lock serializes concurrent FSRS updates.
    stats = await _lock_stats(session, user_id, sense_id)

    if stats is None:
        mastery_before = 0
        state = first_review(correct)
        stats = UserSenseStats(
            user_id=user_id,
            sense_id=sense_id,
            stability=state.stability,
            difficulty=state.difficulty,
            mastery=mastery_of(state.stability),
            interval_days=state.interval_days,
            last_review_date=now,
            next_review_date=_add_days(now, state.interval_days),
            review_count=1,
            lapse_count=0 if correct else 1,
            status=SenseStatus.review if correct else SenseStatus.learning,
        )
        session.add(stats)
        applied = True
    else:
        mastery_before = stats.mastery
        # Only the first attempt in the session mutates stability.
        applied = first_attempt
        if applied:
            state = next_state(
                stats.stability, stats.difficulty, correct, stats.last_review_date, now
            )
            stats.stability = state.stability
            stats.difficulty = state.difficulty
            stats.mastery = mastery_of(state.stability)
            stats.interval_days = state.interval_days
            stats.last_review_date = now
            stats.next_review_date = _add_days(now, state.interval_days)
            stats.review_count += 1
            if not correct:
                stats.lapse_count += 1

    mastery_after = stats.mastery

    # 4. review_log only records attempts that actually moved S (first attempts).
    if applied:
        session.add(
            ReviewLog(
                user_id=user_id,
                sense_id=sense_id,
                stability_before=0.0 if mastery_before == 0 else stats.stability,
                stability_after=stats.stability,
                mastery_before=mastery_before,
                mastery_after=mastery_after,
                grade=grade,
            )
        )

    # 5. Persist the verdict to responses (recoverable if a Centrifugo push is missed).
    session.add(
        Response(
            user_id=user_id,
            sense_id=sense_id,
            question_id=str(question_id),
            is_correct=correct,
            grade_status=grading.grade_status_for(score),
            grade_score=score.score,
            grade_feedback=score.feedback,
            graded_at=now,
        )
    )
    await session.commit()
    seen_senses.add(sense_id)

    return AnswerOutcome(
        sense_id=sense_id,
        is_correct=correct,
        grade_score=score.score,
        grade_feedback=score.feedback,
        mastery_before=mastery_before,
        mastery_after=mastery_after,
        stability_after=stats.stability,
        first_attempt=applied,
    )


async def apply_verdict(
    session: AsyncSession,
    client: LexiClient,
    response_id: UUID,
    now: datetime,
) -> AnswerOutcome | None:
    """Resolve a PENDING async (WRITE) grade — idempotent across arq retries.

    The ``responses.grade_status`` column is the terminal marker: a row already
    ``graded`` returns None (a retried/double-fired job no-ops, never re-billing
    the LLM). Re-fetches the authoritative question by id, grades via lexi, then
    applies the FSRS update under the per-(user,sense) lock and persists the
    verdict onto the SAME response row.
    """
    response = await session.get(Response, response_id, with_for_update=True)
    if response is None:
        raise NotFoundError("response_not_found")
    if response.grade_status == GradeStatus.graded:
        return None  # already terminal — idempotent no-op

    question = await client.get_question(int(response.question_id))
    if question is None:
        raise NotFoundError("question_not_found")

    score = await client.grade(question, response.grade_feedback or "")
    correct = score.correct
    grade = grading.fsrs_grade(score)
    sense_id = response.sense_id
    user_id = response.user_id

    stats = await _lock_stats(session, user_id, sense_id)
    if stats is None:
        mastery_before = 0
        state = first_review(correct)
        stats = UserSenseStats(
            user_id=user_id,
            sense_id=sense_id,
            stability=state.stability,
            difficulty=state.difficulty,
            mastery=mastery_of(state.stability),
            interval_days=state.interval_days,
            last_review_date=now,
            next_review_date=_add_days(now, state.interval_days),
            review_count=1,
            lapse_count=0 if correct else 1,
            status=SenseStatus.review if correct else SenseStatus.learning,
        )
        session.add(stats)
    else:
        mastery_before = stats.mastery
        state = next_state(
            stats.stability, stats.difficulty, correct, stats.last_review_date, now
        )
        stats.stability = state.stability
        stats.difficulty = state.difficulty
        stats.mastery = mastery_of(state.stability)
        stats.interval_days = state.interval_days
        stats.last_review_date = now
        stats.next_review_date = _add_days(now, state.interval_days)
        stats.review_count += 1
        if not correct:
            stats.lapse_count += 1

    session.add(
        ReviewLog(
            user_id=user_id,
            sense_id=sense_id,
            stability_before=0.0 if mastery_before == 0 else stats.stability,
            stability_after=stats.stability,
            mastery_before=mastery_before,
            mastery_after=stats.mastery,
            grade=grade,
        )
    )

    # Flip the SAME response row to terminal — the idempotency marker.
    response.is_correct = correct
    response.grade_status = GradeStatus.graded
    response.grade_score = score.score
    response.grade_feedback = score.feedback
    response.graded_at = now
    await session.commit()

    return AnswerOutcome(
        sense_id=sense_id,
        is_correct=correct,
        grade_score=score.score,
        grade_feedback=score.feedback,
        mastery_before=mastery_before,
        mastery_after=stats.mastery,
        stability_after=stats.stability,
        first_attempt=True,
    )


async def _lock_stats(
    session: AsyncSession, user_id: UUID, sense_id: int
) -> UserSenseStats | None:
    """SELECT ... FOR UPDATE the per-(user,sense) row (row lock, or None if new)."""
    result = await session.execute(
        select(UserSenseStats)
        .where(
            UserSenseStats.user_id == user_id,
            UserSenseStats.sense_id == sense_id,
        )
        .with_for_update()
    )
    return result.scalars().first()


def _add_days(now: datetime, days: float):
    from datetime import timedelta

    return now + timedelta(days=days)
