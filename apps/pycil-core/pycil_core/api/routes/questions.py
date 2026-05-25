"""Question routes — fetch + check."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.schemas.question import (
    QuestionCheckRequest,
    QuestionCheckResponse,
    QuestionFetchResponse,
)
from pycil_core.services import question_service

router = APIRouter(tags=["questions"])


@router.get(
    "/definitions/{definition_id}/question",
    response_model=QuestionFetchResponse,
)
async def fetch_question(
    definition_id: int,
    user: UserDep,  # noqa: ARG001
    session: SessionDep,
    difficulty: str = Query("easy", pattern="^(easy|medium|hard)$"),
) -> QuestionFetchResponse:
    return await question_service.get_or_generate(
        session, definition_id, difficulty
    )


@router.post(
    "/questions/{question_id}/check",
    response_model=QuestionCheckResponse,
)
async def check_question(
    question_id: UUID,
    payload: QuestionCheckRequest,
    user: UserDep,  # noqa: ARG001
    session: SessionDep,
) -> QuestionCheckResponse:
    return await question_service.check_answer(
        session, question_id, payload.selected_index
    )
