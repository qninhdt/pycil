"""grade_answer: settle a PENDING (llm) verdict — idempotent.

The learning service's ``apply_verdict`` is the source of truth: it claims a fenced
lease (so an arq retry never re-bills the judge), calls the judge-backed
``LexiconEngine.evaluate_answer``, and — once settled — applies the checkpoint
consequence (one FSRS update per session/sense, reading the durable
requested/served levels off the response row). The job then converges the durable
task snapshot, which is what the browser is subscribed to.
"""

from datetime import UTC, datetime
from uuid import UUID

from pycil.db.redis import get_redis
from pycil.learning.application import service
from pycil.learning.infra.models import GradeStatus, Response
from pycil.tasks.application import service as task_service
from pycil.tasks.domain.work_keys import grading_work_key
from pycil.tasks.infra.models import AsyncTaskStatus
from shared.realtime.payloads import GradingResult

from pycil_worker.context import ReadyWorkerContext


def _task_result(response: Response) -> dict:
    """The durable task snapshot, built from a persisted row.

    `GradingResult.to_dict()` is the single definition of this wire shape. Three
    hand-written copies of the same nine keys existed here — one per code path — so
    adding a field meant finding all three, and the SSE payload published from the
    same function already went through the dataclass while the task snapshot did not.
    """
    return GradingResult(
        response_id=str(response.id),
        sense_id=response.sense_id,
        is_correct=bool(response.is_correct),
        grade_score=response.grade_score or 0.0,
        grade_feedback=response.grade_feedback,
        mastery_before=response.mastery_before,
        mastery_after=response.mastery_after,
        render_format=response.render_format or "free_text",
        reveal=response.reveal,
    ).to_dict()


def _outcome_result(outcome) -> dict:
    """The same snapshot, built from a fresh grading outcome."""
    return GradingResult(
        response_id=str(outcome.response_id),
        sense_id=outcome.sense_id,
        is_correct=bool(outcome.is_correct),
        grade_score=outcome.grade_score or 0.0,
        grade_feedback=outcome.grade_feedback,
        mastery_before=outcome.mastery_before,
        mastery_after=outcome.mastery_after,
        render_format=outcome.render_format,
        reveal=outcome.reveal,
    ).to_dict()


async def _converge_task_snapshot(ctx: ReadyWorkerContext, response_id: str, result: dict) -> str:
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
        claimed = await task_service.claim_task(session, task.id, ctx.get("worker_id", "worker"))
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


async def grade_answer_v1(ctx: ReadyWorkerContext, owner_uid: str, response_id: str) -> dict:
    """Grade by response id, for the pending-grade reconciler.

    One function rather than the three that used to spell this: `grade_answer`
    held the body, `grade_answer_v1` forwarded to it verbatim to "retain
    `grade_answer` while old jobs drain", and both were registered. There were no
    old jobs to drain — the queue this guarded against has never held any — so the
    forwarder and its target were one name too many for one operation.

    `grade_answer_task` remains separate and is what producers enqueue. This entry
    point exists only because the reconciler re-enqueues by response id, which is
    also why `_converge_task_snapshot` has to go looking for the task afterwards.
    """
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

    task_state = await _converge_task_snapshot(
        ctx,
        response_id,
        _outcome_result(outcome),
    )
    return {"status": "graded", "is_correct": outcome.is_correct, "task": task_state}


async def grade_answer_task(
    ctx: ReadyWorkerContext, task_id: str, owner_uid: str, response_id: str
) -> dict:
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
                result = _outcome_result(outcome)
    except Exception:
        async with ctx["session_factory"]() as session:
            updated = await task_service.transition_task(
                session,
                task_uuid,
                lease_token=task.lease_token,
                lease_fence=task.lease_fence,
                status=AsyncTaskStatus.FAILED,
                error_code="answer_grading_failed",
            )
        return {"status": "failed" if updated else "stale"}
    async with ctx["session_factory"]() as session:
        updated = await task_service.transition_task(
            session,
            task_uuid,
            lease_token=task.lease_token,
            lease_fence=task.lease_fence,
            status=AsyncTaskStatus.SUCCEEDED,
            result=result,
        )
    if updated:
        return {"status": "graded", "is_correct": result["isCorrect"]}
    return {"status": "stale"}
