"""Learning service: the FSRS-backed answer flow.

The verdict comes ENTIRELY from lexi-ai — the server re-fetches the authoritative
question by id (never trusts a client-supplied payload), grades via the port,
then applies the FSRS update under a per-(user,sense) row lock so a concurrent
double-answer applies exactly one first-attempt stability update.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from shared.fsrs import mastery as mastery_of
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import NotFoundError
from pycil.content.lexi_port import LexiClient
from pycil.learning import grading
from pycil.learning.fsrs_wrapper import first_review, next_state
from pycil.learning.models import (
    GradeStatus,
    Response,
    ReviewLog,
    SenseStatus,
    SessionSenseAttempt,
    UserSenseStats,
)


@dataclass
class AnswerOutcome:
    response_id: UUID
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
    # The lease is five minutes. Keep the provider call below it so a queued
    # reconcile job cannot reclaim a still-running grade request.
    score = await asyncio.wait_for(client.grade(question, raw_answer), timeout=240)
    response = Response(
        user_id=user_id,
        session_id=session_id,
        sense_id=sense_id,
        question_id=str(question_id),
        raw_answer=None,
    )
    session.add(response)
    await session.flush()
    outcome = await _apply_resolved_verdict(session, response, score, now)
    await session.commit()
    seen_senses.add(sense_id)
    return outcome


async def apply_verdict(
    session: AsyncSession,
    client: LexiClient,
    response_id: UUID,
    now: datetime,
) -> AnswerOutcome | None:
    """Resolve a PENDING async (WRITE) grade — idempotent across arq retries.

    The ``responses.grade_status`` column is the terminal marker: a row already
    ``graded`` returns None (a retried/double-fired job no-ops, never repeats provider work
    the LLM). Re-fetches the authoritative question by id, grades via lexi, then
    applies the FSRS update under the per-(user,sense) lock and persists the
    verdict onto the SAME response row.
    """
    response = await session.get(Response, response_id, with_for_update=True)
    if response is None:
        raise NotFoundError("response_not_found")
    if response.grade_status != GradeStatus.pending:
        return None  # already terminal — idempotent no-op

    # Claim a short fenced lease, commit, then call the provider outside any DB
    # transaction. A later worker may reclaim only after expiry.
    if (
        response.grading_lease_expires_at is not None
        and response.grading_lease_expires_at > now
    ):
        return None
    lease_owner = uuid4().hex
    response.grading_lease_owner = lease_owner
    response.grading_fence += 1
    fence = response.grading_fence
    response.grading_lease_expires_at = now + timedelta(minutes=5)
    raw_answer = response.raw_answer
    question_id = int(response.question_id)
    await session.commit()

    question = await client.get_question(question_id)
    if question is None:
        raise NotFoundError("question_not_found")

    if raw_answer is None:
        raise NotFoundError("response_raw_answer_missing")
    score = await client.grade(question, raw_answer)

    response = await session.get(Response, response_id, with_for_update=True)
    if (
        response is None
        or response.grade_status != GradeStatus.pending
        or response.grading_lease_owner != lease_owner
        or response.grading_fence != fence
    ):
        return None
    outcome = await _apply_resolved_verdict(session, response, score, now)
    await session.commit()
    return outcome


async def _apply_resolved_verdict(
    session: AsyncSession, response: Response, score, now: datetime
) -> AnswerOutcome:
    """Apply every resolved verdict through one FSRS/log/response path.

    The synchronous route creates a terminal response first; the worker passes
    its fenced pending row. Both therefore share the same first-attempt claim,
    row lock, review-log snapshot, and terminal response mutation.
    """
    correct = score.correct
    sense_id = response.sense_id
    user_id = response.user_id
    first_attempt = await _claim_first_attempt(
        session, user_id, response.session_id or f"response:{response.id}", sense_id
    )
    stats = await _lock_stats(session, user_id, sense_id)
    if stats is None:
        mastery_before = 0
        stability_before = 0.0
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
        stability_before = stats.stability
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

    if applied:
        session.add(
            ReviewLog(
                user_id=user_id,
                sense_id=sense_id,
                stability_before=stability_before,
                stability_after=stats.stability,
                mastery_before=mastery_before,
                mastery_after=stats.mastery,
                grade=grading.fsrs_grade(score),
            )
        )

    response.is_correct = correct
    response.grade_status = grading.grade_status_for(score)
    response.grade_score = score.score
    response.grade_feedback = score.feedback
    response.mastery_before = mastery_before
    response.mastery_after = stats.mastery
    response.raw_answer = None
    response.grading_lease_owner = None
    response.grading_lease_expires_at = None
    response.graded_at = now
    return AnswerOutcome(
        response_id=response.id,
        sense_id=sense_id,
        is_correct=correct,
        grade_score=score.score,
        grade_feedback=score.feedback,
        mastery_before=mastery_before,
        mastery_after=stats.mastery,
        stability_after=stats.stability,
        first_attempt=applied,
    )


async def create_pending_response(
    session: AsyncSession,
    *,
    user_id: UUID,
    session_id: str,
    sense_id: int,
    question_id: int,
    raw_answer: str,
    idempotency_key: str,
) -> Response:
    """Persist/reuse one async-grade outbox row for an issued question."""
    stmt = (
        insert(Response)
        .values(
            user_id=user_id,
            session_id=session_id,
            sense_id=sense_id,
            question_id=str(question_id),
            raw_answer=raw_answer,
            idempotency_key=idempotency_key,
            grade_status=GradeStatus.pending,
        )
        .on_conflict_do_update(
            index_elements=[Response.user_id, Response.idempotency_key],
            index_where=Response.idempotency_key.is_not(None),
            set_={"idempotency_key": idempotency_key},
        )
        .returning(Response)
    )
    response = (await session.execute(stmt)).scalar_one()
    await session.commit()
    return response


async def _lock_stats(
    session: AsyncSession, user_id: UUID, sense_id: int
) -> UserSenseStats | None:
    """Serialize both existing and absent stats rows before FSRS mutation."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": f"fsrs:{user_id}:{sense_id}"},
    )
    result = await session.execute(
        select(UserSenseStats)
        .where(
            UserSenseStats.user_id == user_id,
            UserSenseStats.sense_id == sense_id,
        )
        .with_for_update()
    )
    return result.scalars().first()


async def _claim_first_attempt(
    session: AsyncSession, user_id: UUID, session_id: str, sense_id: int
) -> bool:
    """Insert the immutable session/sense claim; only one concurrent caller wins."""
    stmt = (
        insert(SessionSenseAttempt)
        .values(user_id=user_id, session_id=session_id, sense_id=sense_id)
        .on_conflict_do_nothing(
            constraint="uq_session_sense_attempt"
        )
        .returning(SessionSenseAttempt.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


def _add_days(now: datetime, days: float):
    from datetime import timedelta

    return now + timedelta(days=days)
