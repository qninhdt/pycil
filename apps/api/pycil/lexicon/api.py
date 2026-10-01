"""Word generation, dictionary search, and sense detail endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import current_user, optional_current_user
from pycil.account.schemas import CurrentUser
from pycil.lexicon import generation
from pycil.lexicon.contracts import LexiReader
from pycil.lexicon.provider import get_lexi_client
from pycil.lexicon.schemas import (
    GenerationCreateRead,
    SenseDetailRead,
    WordRequest,
    WordSearchRead,
)
from pycil.lexicon.views import sense_content
from pycil.lexicon.views import sense_detail as map_sense_detail
from pycil.library import membership, scope
from pycil.platform.database import get_session
from pycil.platform.errors import NotFoundError
from pycil.platform.redis import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["lexicon"])


@router.post("/word-generations", response_model=GenerationCreateRead, status_code=202)
async def request_word(
    body: WordRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> GenerationCreateRead:
    task_id = await generation.request_word_generation(
        session,
        get_redis(),
        background_tasks,
        owner_id=user.id,
        query=body.query,
        provenance="word-search",
        idempotency_key=idempotency_key,
    )
    return GenerationCreateRead(task_id=task_id)


@router.get("/words/search", response_model=list[WordSearchRead])
async def search_words(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    # Anonymous lookup stays available — a shared deck opens from its own link
    # without an account, and the two neighbouring content routes read the same
    # way. The dependency is what makes a *broken* token a rejection instead of
    # being silently downgraded to "no token", and keeps this route from being the
    # only one in the API with no auth boundary at all.
    user: Annotated[CurrentUser | None, Depends(optional_current_user)] = None,
    client: LexiReader = Depends(get_lexi_client),
) -> list[WordSearchRead]:
    del user  # Results are identical for every caller; presence is the contract.
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
                    read_dto.senses = [sense_content(sense) for sense in entry.senses]
                    if not read_dto.pos and entry.senses[0].pos:
                        read_dto.pos = entry.senses[0].pos
            except SQLAlchemyError:
                # One result's enrichment failing still leaves a usable row, so the
                # response is not abandoned. It is logged because the silent version
                # reported a Lexi outage as a successful search with thin results.
                # The word id, never the learner's query.
                #
                # Narrow on purpose. A word the search index knows but the dictionary
                # does not is now a `None` return rather than a raise, so the only
                # thing left to absorb here is Lexi's database being unreachable.
                # Catching every exception meant a genuine defect in the enrichment
                # below — a mapper change, a bad attribute — degraded to a thin row
                # and a warning instead of failing where someone would see it.
                logger.warning(
                    "sense enrichment failed for a search result",
                    extra={"lexi_word_id": result.lexi_word_id},
                )
        output.append(read_dto)
    return output


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
    candidate_decks = await membership.deck_ids_for_sense(session, sense_id)
    viewer_id = user.id if user is not None else None
    if not await scope.readable_deck_ids(session, candidate_decks, viewer_id):
        raise NotFoundError("sense_not_found")
    views = await client.get_senses([sense_id])
    if not views:
        # Membership without content: the sense was regenerated away in Lexi.
        raise NotFoundError("sense_not_found")
    return map_sense_detail(views[0], sense_id)
