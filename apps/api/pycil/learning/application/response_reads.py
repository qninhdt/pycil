"""Owner-scoped reads of durable answer responses."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import NotFoundError
from pycil.learning.domain.schemas import GradeResponse
from pycil.learning.infra.models import Response


async def get_response(
    session: AsyncSession, user_id: UUID, response_id: UUID
) -> GradeResponse:
    """Project one response without allowing another learner to probe its state.

    The owner predicate belongs in the database query, rather than as a later
    Python check: both a missing response and another learner's response are the
    same public ``response_not_found`` result. Pending rows intentionally expose no
    unresolved verdict fields; the task id returned at submission is sufficient for
    realtime subscription, while this endpoint is the durable recovery projection.
    """
    response = await session.scalar(
        select(Response).where(
            Response.id == response_id,
            Response.user_id == user_id,
        )
    )
    if response is None:
        raise NotFoundError("response_not_found")

    return GradeResponse(
        response_id=response.id,
        grade_status=response.grade_status.value,
        sense_id=response.sense_id,
        render_format=response.render_format or "free_text",
        is_correct=response.is_correct,
        grade_score=response.grade_score,
        grade_feedback=response.grade_feedback,
        reveal=response.reveal,
        mastery_before=response.mastery_before,
        mastery_after=response.mastery_after,
    )
