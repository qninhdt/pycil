from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from pycil.app.auth import UserId, Viewer
from pycil.app.dependencies import Config, Runtime, Session
from pycil.app.pagination import strict_query
from pycil.jobs.schemas import Accepted
from pycil.library.models import Node, NodeRole
from pycil.library.schemas import Sources
from pycil.library.senses import sources_page
from pycil.library.types import SourcesPageDict
from pycil.utils.errors import InvalidInput, NotFound
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.generation.tasks import request_generation
from pycil.vocabulary.schemas import (
    Context,
    GenerateWord,
    SearchResult,
    SenseIDs,
    Word,
    WordIDs,
    WordPreview,
)
from pycil.vocabulary.words import get_word, viewer_context, word_context, word_previews

router = APIRouter(prefix="/v1", tags=["vocabulary"])


@router.get("/words:search", response_model=SearchResult, openapi_extra={"security": [{}]})
async def search(
    query: str, viewer: Viewer, resources: Runtime, include_reference: bool = False
) -> SearchResult:
    try:
        return await resources.search.search(query, include_reference=include_reference)
    except InvalidResourceError:
        raise InvalidInput("invalid_lexical_query") from None


@router.get("/words/{word_id}", response_model=Word, openapi_extra={"security": [{}]})
async def word(word_id: int, viewer: Viewer, resources: Runtime) -> Word:
    value = await get_word(
        resources.sessions,
        word_id,
        word_store=resources.word_store,
        sense_store=resources.sense_store,
    )
    if value is None:
        raise NotFound("word_not_found")
    return value


@router.post(
    "/words:batchPreview", response_model=list[WordPreview], openapi_extra={"security": [{}]}
)
async def previews(
    data: WordIDs, viewer: Viewer, session: Session, resources: Runtime, config: Config
) -> list[dict[str, object]]:
    return await word_previews(
        session,
        resources.sessions,
        data.word_ids,
        config.vocabulary.preview,
        sense_store=resources.sense_store,
    )


@router.get("/me/words/{word_id}", response_model=Context)
async def personal_word(
    word_id: int, user: UserId, session: Session, config: Config
) -> dict[str, object]:
    return await word_context(
        session,
        user,
        word_id,
        library_config=config.library,
        study_config=config.study,
        policy=config.vocabulary.preview,
    )


@router.post("/me/senses:batchReadContext", response_model=Context)
async def personal_senses(
    data: SenseIDs, user: UserId, session: Session, config: Config
) -> dict[str, object]:
    return await viewer_context(
        session,
        user,
        data.sense_ids,
        library_config=config.library,
        study_config=config.study,
        policy=config.vocabulary.preview,
    )


@router.get("/me/senses/{sense_id}/decks", response_model=Sources)
async def containing_decks(
    request: Request,
    sense_id: int,
    user: UserId,
    session: Session,
    config: Config,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
) -> SourcesPageDict:
    strict_query(request, {"cursor", "limit"})
    root = await session.scalar(
        select(Node.id).where(Node.owner_id == user, Node.role == NodeRole.LIBRARY_ROOT)
    )
    if root is None:
        raise NotFound("library_root_not_found")
    return await sources_page(session, root, sense_id, user, config.library, cursor, limit)


@router.post("/words:generate", response_model=Accepted, status_code=202)
async def generate(
    data: GenerateWord, user: UserId, config: Config, resources: Runtime, response: Response
) -> Accepted:
    accepted = await request_generation(
        resources.sessions,
        resources.redis,
        resources.broker,
        config.vocabulary,
        config.jobs,
        user,
        data.reference_id,
    )
    response.headers.update({"Location": accepted.status_url, "Retry-After": "2"})
    return accepted
