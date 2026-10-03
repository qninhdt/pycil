from uuid import UUID

from fastapi import APIRouter, Request
from lexi_ai.errors import InvalidResourceError
from lexi_ai.models import SearchResult, Word
from pydantic import BaseModel, ConfigDict, Field

from pycil.account.auth import Actor, Viewer
from pycil.dependencies import Dictionary, Product, Session
from pycil.http import Problem
from pycil.vocabulary.generation import projection, submit
from pycil.vocabulary.models import GenerationStatus, WordGeneration

router = APIRouter(prefix="/v1", tags=["vocabulary"])


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available_id: str = Field(min_length=1, max_length=255)
    target: str = Field(min_length=1, max_length=512)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generation_id: UUID
    status: GenerationStatus
    word_id: int | None
    stage: str | None
    error: str | None
    status_url: str


@router.get("/words/search", response_model=SearchResult, openapi_extra={"security": [{}]})
async def search(query: str, viewer: Viewer, lexicon: Dictionary, include_available: bool = False):
    try:
        return await lexicon.search(query, include_available=include_available)
    except InvalidResourceError:
        raise Problem(422, "invalid_lexical_query") from None


@router.get("/words/{word_id}", response_model=Word, openapi_extra={"security": [{}]})
async def word(word_id: int, viewer: Viewer, lexicon: Dictionary):
    value = await lexicon.get_word(word_id)
    if value is None:
        raise Problem(404, "word_not_found")
    return value


@router.post("/word-generations", status_code=202, response_model=GenerationResult)
async def generate(
    data: GenerationRequest, user: Actor, request: Request, config: Product, lexicon: Dictionary
):
    return await submit(request.app.state.sessions, lexicon, data, config)


@router.get("/word-generations/{generation_id}", response_model=GenerationResult)
async def status(generation_id: UUID, user: Actor, session: Session):
    row = await session.get(WordGeneration, generation_id)
    if row is None:
        raise Problem(404, "generation_not_found")
    return projection(row)
