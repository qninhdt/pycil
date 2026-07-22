"""generate_question: delegate question generation to lexi-ai's QuestionEngine.

Questions are generated + persisted inside lexi-ai's DB (via the port, which
routes to ``lexicon.questions``). The worker publishes the resulting question
ids/payloads to the owner-scoped channel.
"""

from uuid import UUID

from pycil.tasks import service as task_service
from pycil.tasks.models import AsyncTaskStatus

from pycil_worker import realtime


async def generate_question(
    ctx: dict,
    owner_uid: str,
    word_id: int,
    formats: list[str],
    n: int = 1,
    session_id: str | None = None,
    sense_id: int | None = None,
) -> dict:
    # New submissions pass a task UUID as the first argument and no session id.
    # Retain the legacy session-keyed handler for already queued jobs.
    if session_id is None:
        try:
            return await _generate_shared_question(
                ctx, UUID(owner_uid), word_id, formats, n, sense_id
            )
        except ValueError:
            pass
    worker_engine = ctx["lexi_engine"]
    job_id = ctx["job_id"]

    await realtime.publish_job(owner_uid, job_id, "running")

    if sense_id is None:
        return {
            "status": "missing_sense",
            "questions": [],
            "session_id": session_id,
            "sense_id": None,
        }
    questions = await worker_engine.generate_questions(word_id, sense_id, formats, n)
    payloads = [
        {"id": q.id, "sense_id": q.sense_id, "format": q.format}
        for q in questions
    ]
    await realtime.publish_job(owner_uid, job_id, "done")
    return {
        "status": "done",
        "questions": payloads,
        "session_id": session_id,
        "sense_id": sense_id,
    }


async def _generate_shared_question(
    ctx: dict,
    task_id: UUID,
    word_id: int,
    formats: list[str],
    n: int,
    sense_id: int | None,
) -> dict:
    if sense_id is None:
        return {"status": "missing_sense", "questions": []}
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        task = await task_service.claim_task(session, task_id, ctx.get("worker_id", "worker"))
    if task is None:
        return {"status": "duplicate"}
    try:
        questions = await ctx["lexi_engine"].generate_questions(word_id, sense_id, formats, n)
    except Exception:
        async with session_factory() as session:
            failed = await task_service.transition_task(
                session,
                task_id,
                lease_token=task.lease_token,
                lease_fence=task.lease_fence,
                status=AsyncTaskStatus.FAILED,
                error_code="question_generation_failed",
            )
        return {"status": "failed" if failed else "stale"}
    result = {
        "questions": [
            {"id": question.id, "sense_id": question.sense_id, "format": question.format}
            for question in questions
        ]
    }
    async with session_factory() as session:
        completed = await task_service.complete_question_task(
            session,
            task_id,
            lease_token=task.lease_token,
            lease_fence=task.lease_fence,
            result=result,
        )
    return {"status": "done", **result} if completed else {"status": "stale"}
