"""Term routes — POST /decks/{id}/terms."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.schemas.term import DeckTermRead, TermAddRequest, TermAddResponse
from pycil_core.services import job_service, term_service

router = APIRouter(prefix="/decks", tags=["terms"])


@router.get("/{deck_id}/terms", response_model=list[DeckTermRead])
async def list_terms(
    deck_id: UUID, user: UserDep, session: SessionDep
) -> list[DeckTermRead]:
    return await term_service.list_deck_terms(session, user.id, deck_id)


@router.post(
    "/{deck_id}/terms",
    response_model=TermAddResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def add_term(
    deck_id: UUID,
    payload: TermAddRequest,
    user: UserDep,
    session: SessionDep,
) -> TermAddResponse:
    response = await term_service.add_term_to_deck(
        session, user.id, deck_id, payload.value
    )
    enqueue = await job_service.enqueue_generate_term(
        session, user.id, response.term.id
    )
    response.job_id = enqueue["job_id"]
    return response
