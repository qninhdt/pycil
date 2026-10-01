"""Stateless server-side grading for semantic and open-ended questions.

Does not import Redis.
Does not mutate learning state, FSRS memory, or mastery.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from lexi_ai.contracts import AnswerSubmission, Reveal, TextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.schemas import CurrentUser
from pycil.billing.ledger import get_or_create_usage_period, record_usage
from pycil.billing.plans import FeatureKey, rubric_grading_cost
from pycil.lexicon.contracts import LexiReader
from pycil.platform.errors import ConflictError, NotFoundError, ServiceUnavailableError
from pycil.study.models import StudySession
from pycil.study.schemas import GradeAnswerResponse, LearningPlan


def reveal_payload(reveal: Reveal | None) -> dict | None:
    """Serialize a sanctioned post-grade reveal."""
    return None if reveal is None else asdict(reveal)


async def grade_server_question(
    session: AsyncSession,
    client: LexiReader,
    *,
    user: CurrentUser,
    session_id: str | UUID,
    question_id: int,
    answer: str,
    now: datetime | None = None,
) -> GradeAnswerResponse:
    """Grade one semantic question via Lexi/LLM.

    Stateless from the perspective of the learning domain:
    only produces evaluation output and records billing usage.
    """
    moment = now if now is not None else datetime.now(UTC)
    session_uuid = UUID(str(session_id)) if isinstance(session_id, str) else session_id

    study_session = await session.get(StudySession, session_uuid)
    if study_session is None or study_session.user_id != user.id:
        raise NotFoundError("session_not_found")

    plan = LearningPlan.model_validate(study_session.plan)
    plan_item = next((item for item in plan.items if item.question_id == question_id), None)
    if plan_item is None:
        raise ConflictError("question_not_in_plan")

    question = await client.get_question(question_id)
    if question is None:
        raise NotFoundError("question_not_found")

    submission = AnswerSubmission(question_id=question_id, response=TextResponse(answer))
    evaluation = await client.evaluate_answer(question_id, submission)
    if evaluation is None:
        raise ServiceUnavailableError("grading_failed")

    format_name = question.render_kind.value if hasattr(question, "render_kind") else ""
    if plan_item.grading_mode == "server" or format_name == "free_text":
        period = await get_or_create_usage_period(session, user_id=user.id, moment=moment)
        await record_usage(
            session,
            user_id=user.id,
            period_id=period.id,
            event_key=f"level4_grading:{session_uuid}:{question_id}:{moment.timestamp()}",
            feature_key=FeatureKey.LEVEL4_GRADING,
            units=rubric_grading_cost(),
            occurred_at=moment,
        )
        await session.commit()

    outcome = "correct" if bool(evaluation.correct) else "incorrect"
    return GradeAnswerResponse(
        outcome=outcome,
        score=evaluation.score,
        feedback=evaluation.feedback,
        reveal=reveal_payload(evaluation.reveal),
    )
