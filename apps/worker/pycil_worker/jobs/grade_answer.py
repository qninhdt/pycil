"""grade_answer: resolve a PENDING async (WRITE) verdict — idempotent.

The learning service's ``apply_verdict`` is the source of truth: it guards on the
``responses.grade_status`` terminal marker (so an arq retry never re-bills the
LLM), re-fetches the authoritative question by id, grades via lexi, applies the
FSRS update under the per-(user,sense) lock, and persists the verdict. The job
then publishes the result to the owner-scoped grading channel.
"""

from datetime import UTC, datetime
from uuid import UUID

from pycil.content.lexi_port import LexiReader, LexiWorkerEngine
from pycil.learning import service
from pycil.learning.models import GradeStatus, Response
from pycil.tasks import service as task_service
from pycil.tasks.models import AsyncTaskStatus
from shared.realtime.payloads import GradingResult

from pycil_worker import realtime


class _LexiGrader:
    """Combine the scoped reader and engine only for the grading service call."""

    def __init__(self, reader: LexiReader, worker_engine: LexiWorkerEngine) -> None:
        self._reader = reader
        self._worker_engine = worker_engine

    async def get_question(self, question_id: int):
        return await self._reader.get_question(question_id)

    async def grade(self, question, answer: str):
        return await self._worker_engine.grade(question, answer)


def _task_result(response: Response) -> dict:
    return {
        "responseId": str(response.id),
        "senseId": response.sense_id,
        "isCorrect": response.is_correct,
        "gradeScore": response.grade_score,
        "gradeFeedback": response.grade_feedback,
        "masteryBefore": response.mastery_before,
        "masteryAfter": response.mastery_after,
    }


async def grade_answer(ctx: dict, owner_uid: str, response_id: str) -> dict:
    client = _LexiGrader(ctx["lexi_reader"], ctx["lexi_engine"])
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        outcome = await service.apply_verdict(
            session, client, UUID(response_id), datetime.now(UTC)
        )

    if outcome is None:
        # Already terminal — a retry or double-fire. No re-grade, no re-publish.
        return {"status": "duplicate"}

    await realtime.publish_grading(
        owner_uid,
        GradingResult(
            response_id=response_id,
            sense_id=outcome.sense_id,
            is_correct=outcome.is_correct,
            grade_score=outcome.grade_score,
            grade_feedback=outcome.grade_feedback,
            mastery_before=outcome.mastery_before,
            mastery_after=outcome.mastery_after,
        ),
    )
    return {"status": "graded", "is_correct": outcome.is_correct}


async def grade_answer_v1(ctx: dict, owner_uid: str, response_id: str) -> dict:
    """Versioned producer target; retain ``grade_answer`` while old jobs drain."""
    return await grade_answer(ctx, owner_uid, response_id)


async def grade_answer_task(ctx: dict, task_id: str, owner_uid: str, response_id: str) -> dict:
    """Persist grading results in the task registry for SSE subscribers."""
    task_uuid = UUID(task_id)
    async with ctx["session_factory"]() as session:
        task = await task_service.claim_task(session, task_uuid, ctx.get("worker_id", "worker"))
    if task is None:
        return {"status": "duplicate"}
    try:
        async with ctx["session_factory"]() as session:
            outcome = await service.apply_verdict(
                session,
                _LexiGrader(ctx["lexi_reader"], ctx["lexi_engine"]),
                UUID(response_id),
                datetime.now(UTC),
            )
            if outcome is None:
                # A crash after apply_verdict commits leaves the task leased but its
                # response terminal. Rebuild the delivery snapshot without regrading.
                response = await session.get(Response, UUID(response_id))
                if response is None or response.grade_status != GradeStatus.graded:
                    return {"status": "duplicate"}
                result = _task_result(response)
            else:
                result = {
                    "responseId": str(outcome.response_id),
                    "senseId": outcome.sense_id,
                    "isCorrect": outcome.is_correct,
                    "gradeScore": outcome.grade_score,
                    "gradeFeedback": outcome.grade_feedback,
                    "masteryBefore": outcome.mastery_before,
                    "masteryAfter": outcome.mastery_after,
                }
    except Exception:
        async with ctx["session_factory"]() as session:
            updated = await task_service.transition_task(
                session, task_uuid, lease_token=task.lease_token, lease_fence=task.lease_fence,
                status=AsyncTaskStatus.FAILED, error_code="answer_grading_failed",
            )
        return {"status": "failed" if updated else "stale"}
    async with ctx["session_factory"]() as session:
        updated = await task_service.transition_task(
            session, task_uuid, lease_token=task.lease_token, lease_fence=task.lease_fence,
            status=AsyncTaskStatus.SUCCEEDED, result=result,
    )
    if updated:
        return {"status": "graded", "is_correct": result["isCorrect"]}
    return {"status": "stale"}
