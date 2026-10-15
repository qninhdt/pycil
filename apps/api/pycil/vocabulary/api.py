from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from pycil.account.auth import UserId, Viewer
from pycil.app.dependencies import Config, Runtime, Session
from pycil.app.http import Problem
from pycil.app.pagination import strict_query
from pycil.app.projections import (
    Context,
    SenseIDs,
    WordIDs,
    WordPreview,
    viewer_context,
    word_context,
    word_previews,
)
from pycil.jobs.schemas import Accepted
from pycil.library.models import Node, NodeRole
from pycil.library.schemas import Sources
from pycil.library.senses import sources_page
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.generation.tasks import request_generation
from pycil.vocabulary.schemas import GenerateWord, SearchResult, Word
from pycil.vocabulary.words import get_word

router = APIRouter(prefix="/v1", tags=["vocabulary"])


@router.get("/words:search", response_model=SearchResult, openapi_extra={"security": [{}]})
async def search(query: str, viewer: Viewer, resources: Runtime, include_reference: bool = False):
    try:
        return await resources.search.search(query, include_reference=include_reference)
    except InvalidResourceError:
        raise Problem(422, "invalid_lexical_query") from None


@router.get("/words/{word_id}", response_model=Word, openapi_extra={"security": [{}]})
async def word(word_id: int, viewer: Viewer, resources: Runtime):
    value = await get_word(
        resources.sessions,
        word_id,
        word_cache=resources.word_cache,
        sense_cache=resources.sense_cache,
    )
    if value is None:
        raise Problem(404, "word_not_found")
    return value


@router.post(
    "/words:batchPreview", response_model=list[WordPreview], openapi_extra={"security": [{}]}
)
async def previews(
    data: WordIDs, viewer: Viewer, session: Session, resources: Runtime, config: Config
):
    return await word_previews(
        session, resources.sessions, data.word_ids, config, sense_cache=resources.sense_cache
    )


@router.get("/me/words/{word_id}", response_model=Context)
async def personal_word(word_id: int, user: UserId, session: Session, config: Config):
    return await word_context(session, user, config, word_id)


@router.post("/me/senses:batchReadContext", response_model=Context)
async def personal_senses(data: SenseIDs, user: UserId, session: Session, config: Config):
    return await viewer_context(session, user, config, data.sense_ids)


@router.get("/me/senses/{sense_id}/decks", response_model=Sources)
async def containing_decks(
    request: Request,
    sense_id: int,
    user: UserId,
    session: Session,
    config: Config,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
):
    strict_query(request, {"cursor", "limit"})
    root = await session.scalar(
        select(Node.id).where(Node.owner_id == user, Node.role == NodeRole.LIBRARY_ROOT)
    )
    return await sources_page(session, root, sense_id, user, config, cursor, limit)


@router.post("/words:generate", response_model=Accepted, status_code=202)
async def generate(
    data: GenerateWord, user: UserId, config: Config, resources: Runtime, response: Response
):
    accepted = await request_generation(
        resources.sessions,
        resources.redis,
        resources.broker,
        config,
        user,
        data.reference_id,
    )
    response.headers.update({"Location": accepted.status_url, "Retry-After": "2"})
    return accepted
