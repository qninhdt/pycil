"""Content routes: word generation trigger + deck membership + content resolve.

Every deck route is gated by ``require_node_access`` (owner-or-public read,
owner-only write). pycil persists only opaque ``deck_senses`` membership; sense
content is resolved through the LexiReader port at read time.
"""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user, optional_current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import TooManyRequestsError
from pycil.config import settings
from pycil.content import service
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiReader
from pycil.content.schemas import SenseAddRequest, SenseContent, WordRequest, WordSearchRead
from pycil.db.redis import get_arq_pool, get_redis
from pycil.db.session import get_session
from pycil.hierarchy.access import require_node_access
from pycil.jobs import service as jobs_service
from pycil.jobs.schemas import GenerationCreateRead
from pycil.tasks import service as task_service
from pycil.tasks.work_keys import word_work_key

router = APIRouter(tags=["content"])


@router.post("/word-generations", response_model=GenerationCreateRead, status_code=202)
async def request_word(
    body: WordRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> GenerationCreateRead:
    redis = get_redis()
    if not await jobs_service.reserve_quota(redis, user.id):
        # Kept as an existing domain exception until the API-wide 429 mapping lands.
        raise TooManyRequestsError(
            "word_generation_quota_exceeded",
            code="word_generation_quota_exceeded",
            retry_after=3600,
        )
    try:
        submission = await task_service.submit_or_join(
            session,
            kind="word",
            server_work_key=word_work_key(
                jobs_service.normalize_query(body.query),
                settings.lexi_reference_dataset_fingerprint,
            ),
            requester_id=user.id,
            command_kind="word.generate",
            command_id=idempotency_key or f"word:{uuid4()}",
            provenance="word-search",
            dispatch={"query": body.query},
        )
    except Exception:
        await jobs_service.release_inflight_quota(redis, user.id)
        raise
    if not submission.task_created:
        await jobs_service.release_inflight_quota(redis, user.id)
    else:
        # The committed task is the source of truth for the subscriber receipt.
        try:
            pool = await get_arq_pool()
            await pool.enqueue_job("generate_word_task", str(submission.task.id), body.query)
        except Exception:  # noqa: BLE001 - durable reconciliation handles enqueue outages
            pass
    return GenerationCreateRead(
        task_id=submission.task.id,
    )


@router.get("/words/search", response_model=list[WordSearchRead])
async def search_words(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    client: LexiReader = Depends(get_lexi_client),
) -> list[WordSearchRead]:
    results = await client.search(q)
    output: list[WordSearchRead] = []
    for result in results:
        read_dto = WordSearchRead.model_validate(result, from_attributes=True)
        if result.lexi_word_id:
            try:
                entry = await client.get_entry(result.lexi_word_id)
                if entry and entry.senses:
                    read_dto.senses = [
                        SenseContent(
                            sense_id=s.sense_id,
                            definition=s.definition,
                            tier=s.tier,
                            pos=s.pos,
                            cefr_level=s.cefr_level,
                            examples=s.examples,
                        )
                        for s in entry.senses
                    ]
                    if not read_dto.pos and entry.senses[0].pos:
                        read_dto.pos = entry.senses[0].pos
            except Exception:
                pass
        output.append(read_dto)
    return output


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
    client: LexiReader = Depends(get_lexi_client),
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
