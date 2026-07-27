"""grade_answer: settle a PENDING (llm) verdict — idempotent.

The learning service's ``apply_verdict`` is the source of truth: it claims a fenced
lease (so an arq retry never re-bills the judge), calls the judge-backed
``LexiconEngine.evaluate_answer``, and — once settled — applies the checkpoint
consequence through the Phase 7 engine (one FSRS update per session/sense, reading
the durable requested/served levels off the response row).  The job then publishes
the settled result to the owner-scoped grading channel.
"""

from datetime import UTC, datetime
from uuid import UUID

from pycil.db.redis import get_redis
from pycil.learning import service
from pycil.learning.models import GradeStatus, Response
from pycil.tasks import service as task_service
from pycil.tasks.models import AsyncTaskStatus
from pycil.tasks.work_keys import grading_work_key
from shared.realtime.payloads import GradingResult

from pycil_worker import realtime


def _task_result(response: Response) -> dict:
    return {
        "responseId": str(response.id),
        "senseId": response.sense_id,
        "isCorrect": response.is_correct,
        "gradeScore": response.grade_score,
        "gradeFeedback": response.grade_feedback,
        "masteryBefore": response.mastery_before,
        "masteryAfter": response.mastery_after,
        "renderFormat": response.render_format or "free_text",
        "reveal": response.reveal,
    }


async def _converge_task_snapshot(ctx: dict, response_id: str, result: dict) -> str:
    """Settle the durable task for a response graded outside the task job.

    The pending-grade reconciler re-enqueues ``grade_answer_v1`` by response id, not
    by task id. That publishes to the owner-scoped grading channel — which the
    subscribe proxy denies outright — and left the ``AsyncTask`` sitting in QUEUED
    forever, so the snapshot the client actually watches never agreed with a verdict
    that had already been applied.

    The task is located through the same work key that created it, claimed, and
    transitioned. The session lifecycle stays authoritative; this snapshot is an
    accelerator, so every failure to converge is reported and swallowed rather than
    failing a grade that is already durably applied.
    """
    async with ctx["session_factory"]() as session:
        task = await task_service.find_live_task(
            session, kind="grading", work_key=grading_work_key(response_id)
        )
        if task is None:
            return "no-task"
        claimed = await task_service.claim_task(
            session, task.id, ctx.get("worker_id", "worker")
        )
    if claimed is None:
        # Another worker owns the lease, or the task is already terminal.
        return "not-claimable"
    async with ctx["session_factory"]() as session:
        updated = await task_service.transition_task(
            session,
            claimed.id,
            lease_token=claimed.lease_token,
            lease_fence=claimed.lease_fence,
            status=AsyncTaskStatus.SUCCEEDED,
            result=result,
        )
    return "converged" if updated else "stale"


async def grade_answer(ctx: dict, owner_uid: str, response_id: str) -> dict:
    redis = get_redis()
    grader = ctx["lexi_engine"]
    session_factory = ctx["session_factory"]

    async with session_factory() as session:
        outcome = await service.apply_verdict(
            session, redis, grader, UUID(response_id), datetime.now(UTC)
        )

    if outcome is None:
        # Already terminal, or still pending (model not settled) — no re-publish.
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
            render_format=outcome.render_format,
            reveal=outcome.reveal,
        ),
    )
    task_state = await _converge_task_snapshot(
        ctx,
        response_id,
        {
            "responseId": str(outcome.response_id),
            "senseId": outcome.sense_id,
            "isCorrect": outcome.is_correct,
            "gradeScore": outcome.grade_score,
            "gradeFeedback": outcome.grade_feedback,
            "masteryBefore": outcome.mastery_before,
            "masteryAfter": outcome.mastery_after,
            "renderFormat": outcome.render_format,
            "reveal": outcome.reveal,
        },
    )
    return {"status": "graded", "is_correct": outcome.is_correct, "task": task_state}


async def grade_answer_v1(ctx: dict, owner_uid: str, response_id: str) -> dict:
    """Versioned producer target; retain ``grade_answer`` while old jobs drain."""
    return await grade_answer(ctx, owner_uid, response_id)


async def grade_answer_task(ctx: dict, task_id: str, owner_uid: str, response_id: str) -> dict:
    """Persist grading results in the task registry for SSE subscribers."""
    redis = get_redis()
    grader = ctx["lexi_engine"]
    task_uuid = UUID(task_id)
    async with ctx["session_factory"]() as session:
        task = await task_service.claim_task(session, task_uuid, ctx.get("worker_id", "worker"))
    if task is None:
        return {"status": "duplicate"}
    try:
        async with ctx["session_factory"]() as session:
            outcome = await service.apply_verdict(
                session, redis, grader, UUID(response_id), datetime.now(UTC)
            )
            if outcome is None:
                # Either already terminal, or still pending (model not settled).
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
                    "renderFormat": outcome.render_format,
                    "reveal": outcome.reveal,
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
