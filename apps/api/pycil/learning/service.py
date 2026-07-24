"""Learning service: the score/state + FSRS-apply engine (correctness core).

Given a GRADED verdict for a delivered checkpoint, this updates STATE (checkpoint
completion) and SCORE (the sense's single FSRS grade) independently, per the spec
attempt table.  At most ONE FSRS update is applied per (session, sense): ``Again``
immediately on the first disqualifier, or ``Good`` on clean completion of all N
checkpoints.

Idempotency (defense in depth), Postgres-authoritative (F1):
  1. ``session_sense_attempts`` unique claim is the authority for
     "FSRS-applied-once-per-(session,sense)" — the claim winner applies FSRS.
  2. ``pg_advisory_xact_lock`` + ``FOR UPDATE`` serialize the write; claim insert,
     ``user_sense_stats`` mutation, and ``ReviewLog`` commit in ONE transaction.
  3. Redis ``lock_score``/``fsrs_applied`` are an ADVISORY fast-path only, updated
     AFTER the Postgres commit — never before (a crash in that gap would lose the
     grade).

The consume-once bind (F5, Phase 8) guarantees a delivered ``question_id`` enters
this apply path at most once, so ``passed`` is never double-incremented.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from lexi_ai.contracts import AnswerSubmission, Reveal, TextResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from shared.fsrs import mastery as mastery_of
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import NotFoundError
from pycil.content.lexi_port import LexiWorkerEngine
from pycil.learning import grading, session_store
from pycil.learning.fsrs_wrapper import first_review, next_state
from pycil.learning.models import (
    GradeStatus,
    Response,
    ReviewLog,
    SenseStatus,
    SessionSenseAttempt,
    UserSenseStats,
)
from pycil.learning.policy import MAX_RETRIES_PER_CHECKPOINT, REQUIRED_CHECKPOINTS

logger = logging.getLogger(__name__)


@dataclass
class CheckpointOutcome:
    response_id: UUID
    sense_id: int
    is_correct: bool
    grade_score: float | None
    grade_feedback: str | None
    mastery_before: int
    mastery_after: int
    stability_after: float
    applied_grade: str | None  # "again" | "good" | None
    fsrs_applied: bool
    state_action: str  # "complete" | "open_retry"
    render_format: str = "free_text"
    reveal: dict | None = None


async def apply_checkpoint_result(
    session: AsyncSession,
    redis: Redis,
    *,
    response: Response,
    verdict: bool,
    score: float | None,
    feedback: str | None,
    now: datetime,
    render_format: str = "free_text",
    reveal: Reveal | None = None,
) -> CheckpointOutcome:
    """Apply a graded checkpoint verdict to STATE + SCORE (see module docstring).

    ``response`` MUST already carry ``requested_level``/``served_level`` (set at
    delivery/answer time, durable per F3) — this is the single source for the
    fallback disqualifier so the async settle survives Redis expiry.  Commits the
    Postgres transaction, then applies best-effort Redis session-state updates.
    """
    session_id = response.session_id
    user_id = response.user_id
    sense_id = response.sense_id
    requested_level = response.requested_level
    served_level = response.served_level
    is_fallback = (
        requested_level is not None
        and served_level is not None
        and served_level < requested_level
    )

    progress = (
        await session_store.get_progress(redis, session_id, sense_id)
        if session_id
        else None
    )
    is_retry = progress is not None and progress.open_checkpoint is not None

    # --- classify (spec attempt table) ---
    state_action = "complete" if (is_fallback or verdict) else "open_retry"
    disqualifier = is_fallback or (verdict is False and not is_retry)
    passed_before = progress.passed if progress is not None else 0
    passed_after = passed_before + (1 if state_action == "complete" else 0)
    completes = state_action == "complete" and passed_after >= REQUIRED_CHECKPOINTS
    grade_due = "again" if disqualifier else ("good" if completes else None)
    retry_exhausted = (
        progress is not None
        and state_action == "open_retry"
        and progress.retries_used + 1 > MAX_RETRIES_PER_CHECKPOINT
    )
    terminal_reveal = (
        grading.reveal_payload(reveal)
        if state_action == "complete" or retry_exhausted
        else None
    )

    # --- Postgres-authoritative FSRS apply (only when a grade is due) ---
    mastery_before = 0
    mastery_after = 0
    stability_after = 0.0
    fsrs_applied = False
    claim_session_id = session_id or f"response:{response.id}"
    if grade_due is not None:
        correct = grade_due == "good"
        first = await _claim_first_attempt(session, user_id, claim_session_id, sense_id)
        stats = await _lock_stats(session, user_id, sense_id)
        if first:
            fsrs_applied = True
            if stats is None:
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
                    status=SenseStatus.scheduled,
                )
                session.add(stats)
            else:
                mastery_before = stats.mastery
                stability_before = stats.stability
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
                stats.status = SenseStatus.scheduled
            session.add(
                ReviewLog(
                    user_id=user_id,
                    sense_id=sense_id,
                    stability_before=stability_before,
                    stability_after=stats.stability,
                    mastery_before=mastery_before,
                    mastery_after=stats.mastery,
                    grade=grading.fsrs_grade_for(grade_due),
                )
            )
            mastery_after = stats.mastery
            stability_after = stats.stability
        elif stats is not None:
            # Claim lost: another submission already applied this session's grade.
            mastery_before = mastery_after = stats.mastery
            stability_after = stats.stability

    # --- terminal response mutation (same transaction) ---
    response.is_correct = verdict
    response.grade_status = GradeStatus.graded
    response.grade_score = score
    response.grade_feedback = feedback
    response.render_format = render_format
    response.reveal = terminal_reveal
    response.mastery_before = mastery_before
    response.mastery_after = mastery_after
    response.raw_answer = None
    response.grading_lease_owner = None
    response.grading_lease_expires_at = None
    response.graded_at = now
    await session.commit()

    # --- best-effort Redis projection (atomic/idempotent, AFTER durable commit) ---
    if session_id and progress is not None:
        for attempt in range(3):
            try:
                await session_store.apply_checkpoint_projection(
                    redis,
                    session_id,
                    sense_id,
                    response_id=response.id,
                    state_action=state_action,
                    requested_level=requested_level or 0,
                    retries_used=progress.retries_used + 1,
                    failed_round=progress.last_round_used,
                    max_retries=MAX_RETRIES_PER_CHECKPOINT,
                    grade_due=grade_due,
                    fsrs_applied=fsrs_applied,
                )
                break
            except RedisError:
                if attempt == 2:
                    logger.exception(
                        "graded response committed but Redis session projection failed",
                        extra={
                            "response_id": str(response.id),
                            "session_id": session_id,
                            "sense_id": sense_id,
                        },
                    )

    return CheckpointOutcome(
        response_id=response.id,
        sense_id=sense_id,
        is_correct=verdict,
        grade_score=score,
        grade_feedback=feedback,
        mastery_before=mastery_before,
        mastery_after=mastery_after,
        stability_after=stability_after,
        applied_grade=grade_due,
        fsrs_applied=fsrs_applied,
        state_action=state_action,
        render_format=render_format,
        reveal=terminal_reveal,
    )


async def apply_verdict(
    session: AsyncSession,
    redis: Redis,
    grader: LexiWorkerEngine,
    response_id: UUID,
    now: datetime,
) -> CheckpointOutcome | None:
    """Settle a PENDING (llm) grade on the worker — idempotent across arq retries.

    Claims a short fenced lease, calls the judge-backed evaluator outside any DB
    transaction, then re-verifies the lease/fence and applies the settled verdict
    through :func:`apply_checkpoint_result`.  A row already ``graded`` no-ops; an
    evaluation still ``pending`` (model not settled) is left for reconcile.
    """
    response = await session.get(Response, response_id, with_for_update=True)
    if response is None:
        raise NotFoundError("response_not_found")
    if response.grade_status != GradeStatus.pending:
        return None
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
    question_id = response.question_id
    await session.commit()

    if raw_answer is None:
        raise NotFoundError("response_raw_answer_missing")
    evaluation = await grader.evaluate_answer(
        question_id,
        AnswerSubmission(
            question_id=str(question_id),
            response=TextResponse(text=raw_answer),
        ),
    )
    if evaluation is None or evaluation.status == "pending":
        return None  # not settled yet — reconcile retries

    response = await session.get(Response, response_id, with_for_update=True)
    if (
        response is None
        or response.grade_status != GradeStatus.pending
        or response.grading_lease_owner != lease_owner
        or response.grading_fence != fence
    ):
        return None
    return await apply_checkpoint_result(
        session,
        redis,
        response=response,
        verdict=bool(evaluation.correct),
        score=evaluation.score,
        feedback=evaluation.feedback,
        now=now,
        render_format=response.render_format or "free_text",
        reveal=evaluation.reveal,
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
    requested_level: int | None,
    served_level: int | None,
    render_format: str,
) -> Response:
    """Persist/reuse one async-grade outbox row (carries durable levels, F3)."""
    stmt = (
        insert(Response)
        .values(
            user_id=user_id,
            session_id=session_id,
            sense_id=sense_id,
            question_id=question_id,
            raw_answer=raw_answer,
            idempotency_key=idempotency_key,
            grade_status=GradeStatus.pending,
            requested_level=requested_level,
            served_level=served_level,
            render_format=render_format,
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
        .on_conflict_do_nothing(constraint="uq_session_sense_attempt")
        .returning(SessionSenseAttempt.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


def _add_days(now: datetime, days: float) -> datetime:
    return now + timedelta(days=days)
