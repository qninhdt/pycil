"""Answer-safe binding, synchronous grading, and answer compensation."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from lexi_ai.contracts import Evaluation, PresentedQuestion
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError, ServiceUnavailableError
from pycil.learning import grading, service, session_store
from pycil.learning.delivery import render_format
from pycil.learning.models import Response
from pycil.policy.policy import depth_stage_name
from pycil.ports.lexi import LexiReader

logger = logging.getLogger(__name__)

# The provider p99 is intentionally the only value to calibrate later. It is a
# hard boundary: a timed-out free-text answer is not persisted or graded.
FREE_TEXT_GRADE_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class GradedNow:
    response_id: UUID
    sense_id: int
    render_format: str
    grade_status: str
    is_correct: bool
    grade_score: float | None
    grade_feedback: str | None
    reveal: dict | None
    mastery_before: int
    mastery_after: int
    depth_before: int
    depth_after: int
    depth_stage_name: str


@dataclass(frozen=True)
class UngradedReask:
    sense_id: int
    render_format: str
    grade_status: str
    is_correct: bool
    grade_score: float | None
    grade_feedback: str | None
    reveal: dict | None


SubmitOutcome = GradedNow | UngradedReask


@dataclass(frozen=True)
class _Bound:
    question: PresentedQuestion
    sense_id: int
    requested_level: int
    served_level: int
    render_format: str
    kind: str
    delivery_round: int


async def submit(
    session: AsyncSession,
    redis: Redis,
    client: LexiReader,
    *,
    user: CurrentUser,
    session_id: str,
    question_id: int,
    answer: str,
    now: datetime,
) -> SubmitOutcome:
    """Grade one delivered assessment, or finish an ungraded re-ask."""
    existing = await _response_for_question(
        session, user.id, session_id, question_id
    )
    if existing is not None:
        await _repair_projection(redis, session, existing)
        return _graded_outcome(existing)

    question, sense_id = await _resolve_question(
        redis, client, session_id=session_id, question_id=question_id
    )
    delivery = await session_store.get_delivery(redis, session_id, sense_id)
    existing = await _existing_response(session, user.id, session_id, sense_id)
    if existing is not None:
        if existing.question_id == question_id:
            await _repair_projection(redis, session, existing)
            return _graded_outcome(existing)
        # A second GRADED answer for one sense in one session is the duplicate this
        # guard exists to refuse. A re-ask is the opposite case and must not be
        # caught by it: it is the delivery that follows a graded answer by design,
        # it writes no second response, and refusing it here would make the one
        # ungraded re-ask per sense unreachable — the sense is always already
        # graded, because that is what scheduled the re-ask.
        if delivery is None or delivery.kind != "reask":
            raise ConflictError("sense_already_graded")

    if (
        delivery is None
        or delivery.question_id != question_id
        or delivery.kind not in {"grade", "reask"}
    ):
        raise ConflictError("question_not_issued_for_session")
    claim_token = await session_store.claim_delivery(
        redis, session_id, sense_id, question_id
    )
    if claim_token is None:
        raise ConflictError("question_submission_in_progress")

    progress = await session_store.get_progress(redis, session_id, sense_id)
    if progress is None:
        await session_store.release_delivery_claim(
            redis, session_id, sense_id, question_id, claim_token
        )
        raise ConflictError("question_not_issued_for_session")
    bound = _Bound(
        question=question,
        sense_id=sense_id,
        requested_level=(
            progress.requested_level
            if delivery.kind == "grade"
            else int(
                progress.reask_level or question.difficulty_level
            )
        ),
        served_level=question.difficulty_level,
        render_format=render_format(question),
        kind=delivery.kind,
        delivery_round=delivery.round_index,
    )
    try:
        evaluation = await _evaluate(client, question, answer)
        if bound.kind == "reask":
            if delivery.delivery_id is None:
                raise ConflictError("reask_delivery_id_missing")
            await service.charge_reask(
                session,
                user_id=user.id,
                delivery_id=delivery.delivery_id,
                render_format=bound.render_format,
            )
            if not await session_store.complete_reask(
                redis, session_id, sense_id, claim_token=claim_token
            ):
                raise ConflictError("question_not_issued_for_session")
            return UngradedReask(
                sense_id=sense_id,
                render_format=bound.render_format,
                grade_status="ungraded",
                is_correct=bool(evaluation.correct),
                grade_score=evaluation.score,
                grade_feedback=evaluation.feedback,
                reveal=grading.reveal_payload(evaluation.reveal),
            )

        response = Response(
            user_id=user.id,
            session_id=session_id,
            sense_id=sense_id,
            question_id=question_id,
            requested_level=bound.requested_level,
            served_level=bound.served_level,
            idempotency_key=f"{session_id}:{sense_id}",
        )
        session.add(response)
        await session.flush()
        outcome = await service.apply_answer(
            session,
            redis,
            response=response,
            verdict=bool(evaluation.correct),
            score=evaluation.score,
            feedback=evaluation.feedback,
            now=now,
            delivery_round=bound.delivery_round,
            render_format=bound.render_format,
            reveal=evaluation.reveal,
            claim_token=claim_token,
        )
        return GradedNow(
            response_id=outcome.response_id,
            sense_id=outcome.sense_id,
            render_format=outcome.render_format,
            grade_status="graded",
            is_correct=outcome.is_correct,
            grade_score=outcome.grade_score,
            grade_feedback=outcome.grade_feedback,
            reveal=outcome.reveal,
            mastery_before=outcome.mastery_before,
            mastery_after=outcome.mastery_after,
            depth_before=outcome.depth_before,
            depth_after=outcome.depth_after,
            depth_stage_name=outcome.depth_stage_name,
        )
    except Exception:
        await session.rollback()
        existing = await _existing_response(session, user.id, session_id, sense_id)
        if existing is not None and existing.question_id == question_id:
            await _repair_projection(redis, session, existing)
            return _graded_outcome(existing)
        await session_store.release_delivery_claim(
            redis, session_id, sense_id, question_id, claim_token
        )
        raise


async def _existing_response(
    session: AsyncSession, user_id: UUID, session_id: str, sense_id: int
) -> Response | None:
    return await session.scalar(
        select(Response).where(
            Response.user_id == user_id,
            Response.session_id == session_id,
            Response.sense_id == sense_id,
        )
    )


async def _response_for_question(
    session: AsyncSession, user_id: UUID, session_id: str, question_id: int
) -> Response | None:
    return await session.scalar(
        select(Response).where(
            Response.user_id == user_id,
            Response.session_id == session_id,
            Response.question_id == question_id,
        )
    )


def _graded_outcome(response: Response) -> GradedNow:
    if response.id is None:
        raise ConflictError("response_not_ready")
    depth = response.depth_after or 0
    return GradedNow(
        response_id=response.id,
        sense_id=response.sense_id,
        render_format=response.render_format or "",
        grade_status="graded",
        is_correct=bool(response.is_correct),
        grade_score=response.grade_score,
        grade_feedback=response.grade_feedback,
        reveal=response.reveal,
        mastery_before=response.mastery_before or 0,
        mastery_after=response.mastery_after or 0,
        depth_before=response.depth_before or 0,
        depth_after=depth,
        depth_stage_name=depth_stage_name(depth),
    )


async def _repair_projection(
    redis: Redis, session: AsyncSession, response: Response
) -> None:
    """Rebuild the disposable cursor from an answer that already committed."""
    if response.id is None or response.session_id is None:
        return
    meta = await session_store.get_meta(redis, response.session_id)
    if meta is None:
        return
    progress = await session_store.get_progress(
        redis, response.session_id, response.sense_id
    )
    if progress is None:
        return
    await session_store.apply_grade_projection(
        redis,
        response.session_id,
        response.sense_id,
        response_id=response.id,
        served_level=response.served_level or 1,
        correct=bool(response.is_correct),
        failed_round=(
            progress.delivery_round
            if progress.delivery_round is not None
            else meta.round_index
        ),
    )


async def _resolve_question(
    redis: Redis,
    client: LexiReader,
    *,
    session_id: str,
    question_id: int,
) -> tuple[PresentedQuestion, int]:
    """Re-fetch the issued question; never trust a client-supplied payload."""
    question = await client.get_question(question_id)
    sense_id: int | None = None
    if question is not None and question.sense_id is not None:
        sense_id = question.sense_id
    if question is None or sense_id is None:
        await session_store.reopen_bound_delivery(redis, session_id, question_id)
        raise ConflictError("question_not_available")
    if question.interaction != "assessment":
        await session_store.reopen_bound_delivery(redis, session_id, question_id)
        raise ConflictError("question_not_assessable")
    return question, sense_id


async def _evaluate(
    client: LexiReader, question: PresentedQuestion, answer: str
) -> Evaluation:
    """Return a settled verdict or a typed refusal with no durable side effect."""
    submission = grading.answer_submission(question, answer)
    try:
        if render_format(question) == "free_text":
            async with asyncio.timeout(FREE_TEXT_GRADE_TIMEOUT_SECONDS):
                evaluation = await client.evaluate_answer(question.question_id, submission)
        else:
            evaluation = await client.evaluate_answer(question.question_id, submission)
    except TimeoutError as error:
        raise ServiceUnavailableError("free_text_grade_timeout") from error
    if evaluation is None:
        raise ConflictError("question_not_assessable")
    if evaluation.status != "graded":
        raise ServiceUnavailableError("free_text_grade_unavailable")
    return evaluation
