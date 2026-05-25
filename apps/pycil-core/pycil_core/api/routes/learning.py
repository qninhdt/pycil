"""Learning routes — start session, fetch question, submit answer."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.schemas.learning import (
    SessionQuestionResponse,
    StartSessionRequest,
    StartSessionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from pycil_core.services import learning_service

router = APIRouter(tags=["learning"])


@router.post(
    "/decks/{deck_id}/learn",
    response_model=StartSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_session(
    deck_id: UUID,
    payload: StartSessionRequest,
    user: UserDep,
    session: SessionDep,
) -> StartSessionResponse:
    return await learning_service.start_session(
        session, user.id, deck_id, payload.session_size
    )


@router.get(
    "/sessions/{session_id}/question",
    response_model=SessionQuestionResponse,
)
async def get_next_question(
    session_id: str, user: UserDep, session: SessionDep
) -> SessionQuestionResponse:
    return await learning_service.next_question(session, user.id, session_id)


@router.post(
    "/sessions/{session_id}/answer",
    response_model=SubmitAnswerResponse,
)
async def submit_answer(
    session_id: str,
    payload: SubmitAnswerRequest,
    user: UserDep,
    session: SessionDep,
) -> SubmitAnswerResponse:
    return await learning_service.submit_answer(
        session,
        user.id,
        session_id,
        payload.question_id,
        payload.selected_index,
    )
