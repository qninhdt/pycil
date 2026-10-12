from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from lexi_ai.errors import InvalidResourceError
from lexi_ai.models import SearchResult, Word
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from pycil.account.auth import Actor, Viewer
from pycil.dependencies import Dictionary, Product, Session
from pycil.http import Problem
from pycil.library.models import Node, NodeRole
from pycil.library.schemas import Sources
from pycil.library.senses import sources_page
from pycil.pagination import strict_query
from pycil.vocabulary.context import (
    Context,
    SenseIDs,
    WordIDs,
    WordPreview,
    viewer_context,
    word_context,
    word_previews,
)

router = APIRouter(prefix="/v1", tags=["vocabulary"])


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_id: str = Field(min_length=1, max_length=255)
    target: str = Field(min_length=1, max_length=512)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID
    status: Literal["RUNNING", "SUCCEEDED", "FAILED"]
    word_id: int | None
    stage: str | None
    error: str | None
    status_url: str


@router.get("/words:search", response_model=SearchResult, openapi_extra={"security": [{}]})
async def search(query: str, viewer: Viewer, lexicon: Dictionary, include_reference: bool = False):
    try:
        return await lexicon.search(query, include_reference=include_reference)
    except InvalidResourceError:
        raise Problem(422, "invalid_lexical_query") from None


@router.get("/words/{word_id}", response_model=Word, openapi_extra={"security": [{}]})
async def word(word_id: int, viewer: Viewer, lexicon: Dictionary):
    value = await lexicon.get_word(word_id)
    if value is None:
        raise Problem(404, "word_not_found")
    return value


@router.post(
    "/words:batchPreview", response_model=list[WordPreview], openapi_extra={"security": [{}]}
)
async def previews(
    data: WordIDs, viewer: Viewer, session: Session, lexicon: Dictionary, config: Product
):
    return await word_previews(session, lexicon, data.word_ids, config)


@router.get("/me/words/{word_id}", response_model=Context)
async def personal_word(word_id: int, user: Actor, session: Session, config: Product):
    return await word_context(session, user.id, config, word_id)


@router.post("/me/senses:batchReadContext", response_model=Context)
async def personal_senses(data: SenseIDs, user: Actor, session: Session, config: Product):
    return await viewer_context(session, user.id, config, data.sense_ids)


@router.get("/me/senses/{sense_id}/decks", response_model=Sources)
async def containing_decks(
    request: Request,
    sense_id: int,
    user: Actor,
    session: Session,
    config: Product,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
):
    strict_query(request, {"cursor", "limit"})
    root = await session.scalar(
        select(Node.id).where(Node.owner_id == user.id, Node.role == NodeRole.LIBRARY_ROOT)
    )
    return await sources_page(session, root, sense_id, user.id, config, cursor, limit)


@router.post("/words:generate", status_code=202, response_model=GenerationResult)
async def generate(data: GenerationRequest, user: Actor, request: Request):
    return await request.app.state.generations.submit(data.target, reference_id=data.reference_id)


@router.get("/word-tasks/{task_id}", response_model=GenerationResult)
async def status(task_id: UUID, user: Actor, request: Request):
    return request.app.state.generations.status(task_id)
