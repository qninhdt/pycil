"""Content routes: word generation trigger + deck membership + content resolve.

Every deck route is gated by ``require_node_access`` (owner-or-public read,
owner-only write). pycil persists only opaque ``deck_senses`` membership; sense
content is resolved through the LexiClient port at read time.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.content import service
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiClient
from pycil.content.schemas import SenseAddRequest, SenseContent, WordRequest
from pycil.db.redis import get_arq_pool
from pycil.db.session import get_session
from pycil.hierarchy.access import require_node_access

router = APIRouter(tags=["content"])


@router.post("/words", status_code=202)
async def request_word(
    body: WordRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> dict[str, str]:
    pool = await get_arq_pool()
    await service.request_word(pool, user.id, body.query)
    return {"status": "enqueued"}


@router.post("/decks/{node_id}/senses", status_code=201)
async def add_sense(
    node_id: UUID,
    body: SenseAddRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    await require_node_access(session, node_id, user, write=True)
    row = await service.add_sense(session, node_id, body.sense_id)
    return {"id": row.id, "senseId": row.sense_id}


@router.delete("/decks/{node_id}/senses/{sense_id}", status_code=204)
async def remove_sense(
    node_id: UUID,
    sense_id: int,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> None:
    await require_node_access(session, node_id, user, write=True)
    await service.remove_sense(session, node_id, sense_id)


@router.get("/decks/{node_id}/items", response_model=list[SenseContent])
async def deck_items(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiClient = Depends(get_lexi_client),
) -> list[SenseContent]:
    # Read access: owner-or-public.
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await service.list_sense_ids(session, node_id)
    views = await service.resolve_senses(client, sense_ids)
    return [
        SenseContent(
            sense_id=v.sense_id,
            definition=v.definition,
            tier=v.tier,
            pos=v.pos,
            cefr_level=v.cefr_level,
            examples=v.examples,
        )
        for v in views
    ]
