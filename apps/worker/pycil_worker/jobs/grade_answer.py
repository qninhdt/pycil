"""grade_answer: resolve a PENDING async (WRITE) verdict — idempotent.

The learning service's ``apply_verdict`` is the source of truth: it guards on the
``responses.grade_status`` terminal marker (so an arq retry never re-bills the
LLM), re-fetches the authoritative question by id, grades via lexi, applies the
FSRS update under the per-(user,sense) lock, and persists the verdict. The job
then publishes the result to the owner-scoped grading channel.
"""

from datetime import UTC, datetime
from uuid import UUID

from pycil.learning import service
from shared.realtime.payloads import GradingResult

from pycil_worker import realtime


async def grade_answer(ctx: dict, owner_uid: str, response_id: str) -> dict:
    client = ctx["lexi_client"]
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
        ),
    )
    return {"status": "graded", "is_correct": outcome.is_correct}
