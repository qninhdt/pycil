from fastapi import APIRouter, Response

from pycil.app.auth import UserId, Viewer
from pycil.app.dependencies import Config, Runtime, Session
from pycil.jobs.schemas import Accepted
from pycil.utils.errors import InvalidInput, NotFound
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.generation.tasks import request_generation
from pycil.vocabulary.schemas import (
    Context,
    GenerateWord,
    SearchResult,
    Word,
    WordIDs,
    WordPreview,
)
from pycil.vocabulary.words import get_word, word_context, word_previews

router = APIRouter(prefix="/v1", tags=["vocabulary"])


@router.get("/words:search", response_model=SearchResult, openapi_extra={"security": [{}]})
async def search(
    viewer: Viewer,
    resources: Runtime,
    query: str | None = None,
    q: str | None = None,
    include_reference: bool = False,
) -> SearchResult:
    target = query or q
    if not target:
        raise InvalidInput("invalid_lexical_query")
    try:
        return await resources.search.search(target, include_reference=include_reference)
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
