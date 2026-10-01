"""Deck membership endpoints owned by the library context."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import current_user, optional_current_user
from pycil.account.schemas import CurrentUser
from pycil.lexicon.contracts import LexiReader
from pycil.lexicon.provider import get_lexi_client
from pycil.lexicon.schemas import SenseAddRequest, SenseContent
from pycil.lexicon.views import sense_content
from pycil.library import membership
from pycil.library.access import require_node_access
from pycil.platform.database import get_session
from pycil.study.engine.policy import strength_stage, strength_stage_name
from pycil.study.models import UserSenseStats

router = APIRouter(tags=["library"])


def _with_progress(content: SenseContent, state: UserSenseStats | None) -> SenseContent:
    if state is None:
        return content
    content.mastery = state.mastery
    content.mastery_stage = strength_stage(state.mastery)
    content.mastery_stage_name = strength_stage_name(state.mastery)
    content.next_review_date = state.next_review_date
    content.review_count = state.review_count
    content.lapse_count = state.lapse_count
    content.status = state.status.value
    return content


@router.post("/decks/{deck_id}/senses", status_code=201)
async def add_sense(
    deck_id: UUID,
    body: SenseAddRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    await require_node_access(session, deck_id, user, write=True)
    row = await membership.add_sense(session, deck_id, body.sense_id)
    return {"id": row.id, "senseId": row.sense_id}


@router.delete("/decks/{deck_id}/senses/{sense_id}", status_code=204)
async def remove_sense(
    deck_id: UUID,
    sense_id: int,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> None:
    await require_node_access(session, deck_id, user, write=True)
    await membership.remove_sense(session, deck_id, sense_id)


@router.get("/decks/{deck_id}/items", response_model=list[SenseContent])
async def deck_items(
    deck_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> list[SenseContent]:
    await require_node_access(session, deck_id, user, write=False)
    sense_ids = await membership.list_sense_ids(session, deck_id)
    senses = await membership.resolve_senses(client, sense_ids)
    state = await membership.learning_state_for(
        session, user.id if user is not None else None, sense_ids
    )
    return [_with_progress(sense_content(sense), state.get(sense.sense_id)) for sense in senses]
