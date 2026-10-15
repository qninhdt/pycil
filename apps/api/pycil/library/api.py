from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response

from pycil.account.auth import UserId, Viewer
from pycil.app.dependencies import Config, Runtime, Session
from pycil.app.pagination import strict_query
from pycil.library import nodes
from pycil.library.access import readable
from pycil.library.models import NodeType
from pycil.library.schemas import (
    NodeCreate,
    NodeDestination,
    NodeDetails,
    NodeMove,
    NodePage,
    NodePatch,
    NodeView,
    NodeViewWithReference,
    SavedDeck,
    SavedNode,
    SenseDelta,
    SensePage,
    SenseSort,
    Sources,
)
from pycil.library.search import search_nodes
from pycil.library.senses import sense_page, sources_page
from pycil.study.enums import LearningState

router = APIRouter(prefix="/v1/nodes", tags=["nodes"])


@router.get("", response_model=NodePage, openapi_extra={"security": [{}]})
async def listing(
    request: Request,
    viewer: Viewer,
    session: Session,
    config: Config,
    parent_id: UUID | None = None,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
    include: str | None = None,
):
    strict_query(request, {"parent_id", "cursor", "limit", "include"})
    return await nodes.list_nodes(
        session,
        viewer,
        parent_id,
        cursor,
        config,
        limit=limit,
        include=include,
    )


@router.post("", status_code=201, response_model=SavedNode)
async def create(data: NodeCreate, user: UserId, session: Session, config: Config):
    return await nodes.create_node(session, user, data, config)


@router.get("/{node_id}:search", response_model=NodePage, openapi_extra={"security": [{}]})
async def scoped_search(
    request: Request,
    node_id: UUID,
    viewer: Viewer,
    session: Session,
    config: Config,
    q: str = Query(max_length=200),
    type: NodeType | None = None,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
    include: str | None = None,
):
    strict_query(request, {"q", "type", "cursor", "limit", "include"})
    return await search_nodes(
        session,
        viewer,
        config,
        node_id=node_id,
        q=q,
        type=type,
        cursor=cursor,
        limit=limit,
        include=include,
    )


@router.get("/{node_id}", response_model=NodeDetails, openapi_extra={"security": [{}]})
async def detail(node_id: UUID, viewer: Viewer, session: Session, config: Config):
    return await nodes.node_details(session, node_id, viewer, config)


@router.patch("/{node_id}", response_model=NodeView)
async def patch(node_id: UUID, data: NodePatch, user: UserId, session: Session, config: Config):
    return await nodes.patch_node(session, user, node_id, data, config)


@router.post("/{node_id}:modifySenses", response_model=SavedDeck)
async def edit_senses(
    node_id: UUID, data: SenseDelta, user: UserId, session: Session, config: Config
):
    return await nodes.patch_senses(session, user, node_id, data, config)


@router.post("/{node_id}:move", response_model=NodeViewWithReference)
async def move(node_id: UUID, data: NodeMove, user: UserId, session: Session, config: Config):
    return await nodes.move_node(session, user, node_id, data, config)


@router.post("/{node_id}:copy", status_code=201, response_model=SavedNode)
async def copy(
    node_id: UUID, data: NodeDestination, user: UserId, session: Session, config: Config
):
    return await nodes.copy_node(session, user, node_id, data, config)


@router.delete("/{node_id}", status_code=204)
async def remove(node_id: UUID, user: UserId, session: Session, config: Config):
    await nodes.delete_node(session, user, node_id, config)
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
    config: Config,
    resources: Runtime,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    sort: Literal[
        SenseSort.SENSE_ID_ASC, SenseSort.LEMMA_ASC, SenseSort.LAST_REVIEWED_DESC
    ] = SenseSort.SENSE_ID_ASC,
    include: str | None = None,
    state: Literal[
        LearningState.ALL, LearningState.NEW, LearningState.DUE, LearningState.NOT_YET_DUE
    ] = LearningState.ALL,
):
    strict_query(request, {"cursor", "limit", "q", "sort", "include", "state"})
    viewer_id = viewer
    node = await readable(session, node_id, viewer_id, config)
    return await sense_page(
        session,
        node,
        viewer_id,
        config,
        resources.sessions,
        cursor,
        state=state,
        q=q,
        sort=sort,
        include=include,
        limit=limit,
        sense_store=resources.sense_store,
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
    config: Config,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int | None = Query(default=None, ge=1, le=100),
):
    strict_query(request, {"cursor", "limit"})
    return await sources_page(session, node_id, sense_id, viewer, config, cursor, limit)
