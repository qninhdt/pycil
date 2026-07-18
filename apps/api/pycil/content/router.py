"""Content routes: word generation trigger + deck membership + content resolve.

Every deck route is gated by ``require_node_access`` (owner-or-public read,
owner-only write). pycil persists only opaque ``deck_senses`` membership; sense
content is resolved through the LexiClient port at read time.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user, optional_current_user
from pycil.auth.schemas import CurrentUser
from pycil.content import service
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiClient
from pycil.content.schemas import SenseAddRequest, SenseContent, WordRequest, WordSearchRead
from pycil.db.redis import get_arq_pool
from pycil.db.session import get_session
from pycil.hierarchy.access import require_node_access
from pycil.jobs import service as jobs_service
from pycil.jobs.schemas import GenerationCreateRead

router = APIRouter(tags=["content"])


@router.post("/word-generations", response_model=GenerationCreateRead, status_code=202)
async def request_word(
    body: WordRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> GenerationCreateRead:
    record, created = await jobs_service.create_or_retrieve_generation(
        session, user.id, body.query, idempotency_key
    )
    if created:
        # The committed row is the source of truth. If Redis is temporarily
        # unavailable, the worker's queued-job reconciler will submit it later.
        try:
            pool = await get_arq_pool()
            await pool.enqueue_job("generate_word", str(user.id), body.query, str(record.id))
        except Exception:  # noqa: BLE001 - durable reconciliation handles enqueue outages
            pass
    return GenerationCreateRead(job_id=record.id, status=record.status)


@router.get("/words/search", response_model=list[WordSearchRead])
async def search_words(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    client: LexiClient = Depends(get_lexi_client),
) -> list[WordSearchRead]:
    results = await client.search(q)
    return [WordSearchRead.model_validate(result, from_attributes=True) for result in results]


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
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
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
