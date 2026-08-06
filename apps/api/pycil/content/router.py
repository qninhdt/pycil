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
from pycil.common.errors import NotFoundError, TooManyRequestsError
from pycil.config import settings
from pycil.content.application import service
from pycil.content.domain.schemas import (
    SenseAddRequest,
    SenseContent,
    SenseDetailRead,
    SenseFormRead,
    SenseReferenceRead,
    SenseRelationRead,
    WordRequest,
    WordSearchRead,
)
from pycil.db.redis import get_arq_pool, get_redis
from pycil.db.session import get_session
from pycil.hierarchy.application import subtree
from pycil.hierarchy.application.access import require_node_access
from pycil.jobs import service as jobs_service
from pycil.jobs.schemas import GenerationCreateRead
from pycil.policy.policy import mastery_stage, mastery_stage_name
from pycil.policy.sense_state import UserSenseStats
from pycil.ports.lexi import LexiReader, SenseView
from pycil.ports.lexi_provider import get_lexi_client
from pycil.tasks.application import service as task_service
from pycil.tasks.domain.work_keys import word_work_key

router = APIRouter(tags=["content"])


def _sense_content(view: SenseView, state: UserSenseStats | None = None) -> SenseContent:
    """Project a Lexi sense view onto the listing DTO (headword, no full record).

    ``state`` is the caller's learning state when the surface has it. Omitted on the
    search path, which has no user scope and must not grow a query.
    """
    content = SenseContent(
        sense_id=view.sense_id,
        definition=view.definition,
        tier=view.tier,
        pos=view.pos,
        cefr_level=view.cefr_level,
        examples=view.examples,
        word=view.word,
        word_id=view.word_id,
    )
    if state is not None:
        content.mastery = state.mastery
        content.mastery_stage = mastery_stage(state.mastery)
        content.mastery_stage_name = mastery_stage_name(state.mastery)
        content.next_review_date = state.next_review_date
        content.review_count = state.review_count
        content.lapse_count = state.lapse_count
        content.status = state.status.value
    return content


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
            dispatch={"query": body.query, "owner_id": str(user.id)},
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
            await pool.enqueue_job(
                "generate_word_task", str(submission.task.id), body.query, str(user.id)
            )
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
    # KNOWN ISSUE, pre-existing and deliberately not fixed here: this issues one
    # cross-boundary get_entry per search result. A batched reader capability is
    # the real fix. Until then, treat the per-result payload as a hot path — see
    # the note on SenseContent before adding a field to it.
    for result in results:
        read_dto = WordSearchRead.model_validate(result, from_attributes=True)
        if result.lexi_word_id:
            try:
                entry = await client.get_entry(result.lexi_word_id)
                if entry and entry.senses:
                    read_dto.senses = [_sense_content(s) for s in entry.senses]
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
    state = await service.learning_state_for(
        session, user.id if user is not None else None, sense_ids
    )
    return [_sense_content(v, state.get(v.sense_id) if v.sense_id else None) for v in views]


@router.get("/senses/{sense_id}", response_model=SenseDetailRead)
async def sense_detail(
    sense_id: int,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> SenseDetailRead:
    """The full lexical record for one sense, authorized owner-or-public.

    A sense is not an owned resource in pycil — it is Lexi content that becomes
    reachable by being a member of a deck. So access is derived: the caller may
    read the sense if at least one deck holding it is readable by them, which is
    the same rule ``require_node_access`` applies to the deck itself.

    Unknown, unreferenced and unreadable all return one 404 with one code, so the
    endpoint cannot be used to probe which senses exist or who has them.
    """
    candidate_decks = await service.deck_ids_for_sense(session, sense_id)
    viewer_id = user.id if user is not None else None
    if not await subtree.readable_deck_ids(session, candidate_decks, viewer_id):
        raise NotFoundError("sense_not_found")
    views = await client.get_senses([sense_id])
    if not views:
        # Membership without content: the sense was regenerated away in Lexi.
        raise NotFoundError("sense_not_found")
    return _sense_detail(views[0], sense_id)


def _sense_detail(view: SenseView, sense_id: int) -> SenseDetailRead:
    """Project a Lexi sense view onto the full-record DTO.

    ``sense_id`` is passed explicitly rather than read off the view: the view's own
    id is optional in Lexi's contract, and the caller already resolved a concrete
    id to authorize against.
    """
    return SenseDetailRead(
        sense_id=sense_id,
        word=view.word,
        word_id=view.word_id,
        definition=view.definition,
        tier=view.tier,
        pos=view.pos,
        cefr_level=view.cefr_level,
        examples=list(view.examples),
        ipa_uk=view.ipa_uk,
        ipa_us=view.ipa_us,
        guideword=view.guideword,
        grammar=list(view.grammar),
        register=view.register,
        connotation=view.connotation,
        collocations=list(view.collocations),
        domain=view.domain,
        usage_note=view.usage_note,
        forms=[SenseFormRead(inf=f.inf, surface=f.surface) for f in view.forms],
        references=[
            SenseReferenceRead(source=r.source, source_ref=r.source_ref) for r in view.references
        ],
        relations=[
            SenseRelationRead(
                rel_type=r.rel_type,
                to_word_display=r.to_word_display,
                to_word_id=r.to_word_id,
                to_word_status=r.to_word_status,
                wsd_state=r.wsd_state,
                to_sense_id=r.to_sense_id,
                to_sense_gloss=r.to_sense_gloss,
            )
            for r in view.relations
        ],
    )
