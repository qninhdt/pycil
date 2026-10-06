from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response

from pycil.account.auth import Actor, Viewer
from pycil.dependencies import Dictionary, Product, Session
from pycil.library import nodes
from pycil.library.access import readable
from pycil.library.models import NodeType
from pycil.library.schemas import (
    DeckSnapshot,
    NodeCreate,
    NodeDetails,
    NodePage,
    NodeSave,
    NodeView,
    SavedNode,
    SensePage,
    Sources,
)
from pycil.library.search import search_nodes
from pycil.library.senses import sense_page, sources_page
from pycil.pagination import strict_query

router = APIRouter(prefix="/v1/nodes", tags=["nodes"])


@router.get("", response_model=NodePage, openapi_extra={"security": [{}]})
async def listing(
    request: Request,
    viewer: Viewer,
    session: Session,
    config: Product,
    parent_id: UUID | None = None,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
    include: str | None = None,
):
    strict_query(request, {"parent_id", "cursor", "limit", "include"})
    return await nodes.list_nodes(
        session,
        viewer.id if viewer else None,
        parent_id,
        cursor,
        config,
        limit=limit,
        include=include,
    )


@router.post("", status_code=201, response_model=SavedNode)
async def create(data: NodeCreate, user: Actor, session: Session, config: Product):
    return await nodes.create_node(session, user.id, data, config)


@router.get("/{node_id}", response_model=NodeDetails, openapi_extra={"security": [{}]})
async def detail(node_id: UUID, viewer: Viewer, session: Session, config: Product):
    return await nodes.node_details(session, node_id, viewer.id if viewer else None, config)


@router.get("/{node_id}/editor", response_model=DeckSnapshot | NodeView)
async def editor(node_id: UUID, user: Actor, session: Session, config: Product):
    return await nodes.editor_snapshot(session, node_id, user.id, config)


@router.put("/{node_id}", response_model=SavedNode)
async def save(node_id: UUID, data: NodeSave, user: Actor, session: Session, config: Product):
    return await nodes.save_node(session, user.id, node_id, data, config)


@router.delete("/{node_id}", status_code=204)
async def remove(node_id: UUID, user: Actor, session: Session, config: Product):
    await nodes.delete_node(session, user.id, node_id, config)
    return Response(status_code=204)


@router.get(
    "/{node_id}/senses",
    response_model=SensePage,
    openapi_extra={"security": [{}]},
)
async def senses(
    request: Request,
    node_id: UUID,
    viewer: Viewer,
    session: Session,
    config: Product,
    lexicon: Dictionary,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    sort: Literal["SENSE_ID_ASC", "LEMMA_ASC", "LAST_REVIEWED_DESC"] = "SENSE_ID_ASC",
    include: str | None = None,
    state: Literal["ALL", "NEW", "DUE", "NOT_YET_DUE"] = "ALL",
):
    strict_query(request, {"cursor", "limit", "q", "sort", "include", "state"})
    viewer_id = viewer.id if viewer else None
    node = await readable(session, node_id, viewer_id, config)
    return await sense_page(
        session,
        node,
        viewer_id,
        config,
        lexicon,
        cursor,
        state=state,
        q=q,
        sort=sort,
        include=include,
        limit=limit,
    )


@router.get(
    "/{node_id}/senses/{sense_id}/sources", response_model=Sources, openapi_extra={"security": [{}]}
)
async def provenance(
    request: Request,
    node_id: UUID,
    sense_id: Annotated[int, Path(gt=0)],
    viewer: Viewer,
    session: Session,
    config: Product,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
):
    strict_query(request, {"cursor", "limit"})
    return await sources_page(
        session, node_id, sense_id, viewer.id if viewer else None, config, cursor, limit
    )


@router.get("/{node_id}/search", response_model=NodePage, openapi_extra={"security": [{}]})
async def scoped_search(
    request: Request,
    node_id: UUID,
    viewer: Viewer,
    session: Session,
    config: Product,
    q: str = Query(max_length=200),
    type: NodeType | None = None,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
    include: str | None = None,
):
    strict_query(request, {"q", "type", "cursor", "limit", "include"})
    return await search_nodes(
        session,
        viewer.id if viewer else None,
        config,
        node_id=node_id,
        q=q,
        type=type,
        cursor=cursor,
        limit=limit,
        include=include,
    )
