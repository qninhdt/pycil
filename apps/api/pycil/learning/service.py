"""Atomic strength/depth application for one settled assessment."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from lexi_ai.contracts import Reveal
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account import credit
from pycil.account.plans import rubric_grading_cost
from pycil.common.errors import ConflictError
from pycil.learning import grading, session_store
from pycil.learning.fsrs import mastery as mastery_of
from pycil.learning.fsrs_wrapper import first_review, next_state
from pycil.learning.models import Response, ReviewLog
from pycil.policy.depth import next_depth_state
from pycil.policy.policy import depth_stage_name
from pycil.policy.sense_state import SenseStatus, UserSenseStats


@dataclass(frozen=True)
class GradedOutcome:
    response_id: UUID
    sense_id: int
    is_correct: bool
    grade_score: float | None
    grade_feedback: str | None
    mastery_before: int
    mastery_after: int
    depth_before: int
    depth_after: int
    depth_stage_name: str
    applied_grade: str
    fsrs_applied: bool
    render_format: str
    reveal: dict | None


async def apply_answer(
    session: AsyncSession,
    redis: Redis,
    *,
    response: Response,
    verdict: bool,
    score: float | None,
    feedback: str | None,
    now: datetime,
    delivery_round: int,
    render_format: str,
    reveal: Reveal | None = None,
    claim_token: str | None = None,
) -> GradedOutcome:
    """Apply exactly one binary FSRS grade and one depth transition.

    The response row, learner-sense mutation, and review log commit together. A
    re-ask never calls this function, so it cannot accidentally create a second
    memory update.
    """
    user_id = response.user_id
    sense_id = response.sense_id
    session_id = response.session_id
    if response.id is None:
        raise ConflictError("response_not_ready")

    # The unique response constraint is the durable one-grade-per-session guard;
    # this read gives a useful domain error when a caller reaches us without the
    # normal consume-once delivery path.
    if session_id is not None:
        duplicate = await session.scalar(
            select(Response.id).where(
                Response.user_id == user_id,
                Response.session_id == session_id,
                Response.sense_id == sense_id,
                Response.id != response.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("sense_already_graded")

    node_id: UUID | None = None
    if session_id:
        meta = await session_store.get_meta(redis, session_id)
        if meta is not None:
            node_id = meta.node_id

    stats = await _lock_stats(session, user_id, sense_id)
    if stats is None:
        stats = UserSenseStats(user_id=user_id, sense_id=sense_id)
        session.add(stats)
        await session.flush()

    mastery_before = stats.mastery
    stability_before = stats.stability
    depth_before = stats.depth_level
    was_new = stats.status == SenseStatus.new or stats.review_count == 0
    if was_new:
        state = first_review(verdict)
        depth_after, streak_after = next_depth_state(0, 0, response.served_level or 1, verdict)
    else:
        state = next_state(
            stats.stability,
            stats.difficulty,
            verdict,
            stats.last_review_date,
            now,
        )
        depth_after, streak_after = next_depth_state(
            stats.depth_level,
            stats.depth_streak,
            response.served_level or 1,
            verdict,
        )
    stats.review_count += 1
    if not verdict:
        stats.lapse_count += 1

    stats.stability = state.stability
    stats.difficulty = state.difficulty
    stats.mastery = mastery_of(state.stability)
    stats.interval_days = state.interval_days
    stats.last_review_date = now
    stats.next_review_date = _add_days(now, state.interval_days)
    stats.status = SenseStatus.scheduled
    stats.depth_level = depth_after
    stats.depth_streak = streak_after

    response.is_correct = verdict
    response.grade_status = "graded"
    response.grade_score = score
    response.grade_feedback = feedback
    response.render_format = render_format
    response.reveal = grading.reveal_payload(reveal)
    response.mastery_before = mastery_before
    response.mastery_after = stats.mastery
    response.depth_before = depth_before
    response.depth_after = depth_after
    response.answered_at = now
    response.graded_at = now

    session.add(
        ReviewLog(
            user_id=user_id,
            sense_id=sense_id,
            node_id=node_id,
            stability_before=stability_before,
            stability_after=stats.stability,
            mastery_before=mastery_before,
            mastery_after=stats.mastery,
            grade=grading.fsrs_grade_for("good" if verdict else "again"),
        )
    )
    if grading.evaluation_mechanism(render_format) == "rubric_judge":
        await credit.debit(
            session,
            user_id,
            kind=credit.CREDIT_KIND_RUBRIC,
            reference_id=response.id,
            amount=rubric_grading_cost(),
        )
    await session.commit()

    if session_id:
        projected = await session_store.apply_grade_projection(
            redis,
            session_id,
            sense_id,
            response_id=response.id,
            served_level=response.served_level or 1,
            correct=verdict,
            failed_round=delivery_round,
            claim_token=claim_token,
        )
        if claim_token is not None and not projected:
            raise ConflictError("study_session_claim_lost")

    return GradedOutcome(
        response_id=response.id,
        sense_id=sense_id,
        is_correct=verdict,
        grade_score=score,
        grade_feedback=feedback,
        mastery_before=mastery_before,
        mastery_after=stats.mastery,
        depth_before=depth_before,
        depth_after=depth_after,
        depth_stage_name=depth_stage_name(depth_after),
        applied_grade="good" if verdict else "again",
        fsrs_applied=True,
        render_format=render_format,
        reveal=response.reveal,
    )


async def _lock_stats(
    session: AsyncSession, user_id: UUID, sense_id: int
) -> UserSenseStats | None:
    """Serialize the existing and absent learner-sense row."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:user_key, :sense_key)"),
        {
            "user_key": int.from_bytes(user_id.bytes[:4], "big", signed=True),
            "sense_key": sense_id % 2**31,
        },
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


def _add_days(now: datetime, days: float) -> datetime:
    return now + timedelta(days=days)


async def charge_reask(
    session: AsyncSession,
    *,
    user_id: UUID,
    delivery_id: UUID,
    render_format: str,
) -> None:
    """Charge a rubric re-ask once without writing a second learning result."""
    if grading.evaluation_mechanism(render_format) != "rubric_judge":
        return
    await credit.debit(
        session,
        user_id,
        kind=credit.CREDIT_KIND_RUBRIC,
        reference_id=delivery_id,
        amount=rubric_grading_cost(),
    )
    await session.commit()
