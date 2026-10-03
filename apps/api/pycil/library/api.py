from uuid import UUID

from fastapi import APIRouter, Query, Response

from pycil.account.auth import Actor, Viewer
from pycil.dependencies import Dictionary, Product, Session
from pycil.library import nodes
from pycil.library.access import readable
from pycil.library.schemas import (
    DeckSenses,
    NodeCreate,
    NodeDetails,
    NodePage,
    NodeSave,
    SavedNode,
    SensePage,
)
from pycil.library.senses import sense_page

router = APIRouter(prefix="/v1/library/nodes", tags=["library"])


@router.get("", response_model=NodePage, openapi_extra={"security": [{}]})
async def listing(
    viewer: Viewer,
    session: Session,
    config: Product,
    parent_id: UUID | None = None,
    after_id: UUID | None = None,
):
    return await nodes.list_nodes(
        session, viewer.id if viewer else None, parent_id, after_id, config
    )


@router.post("", status_code=201, response_model=SavedNode)
async def create(data: NodeCreate, user: Actor, session: Session, config: Product):
    return await nodes.create_node(session, user.id, data, config)


@router.get("/{node_id}", response_model=NodeDetails, openapi_extra={"security": [{}]})
async def detail(
    node_id: UUID, viewer: Viewer, session: Session, config: Product, lexicon: Dictionary
):
    return await nodes.node_details(
        session, node_id, viewer.id if viewer else None, config, lexicon
    )


@router.put("/{node_id}", response_model=SavedNode)
async def save(node_id: UUID, data: NodeSave, user: Actor, session: Session, config: Product):
    return await nodes.save_node(session, user.id, node_id, data, config)


@router.delete("/{node_id}", status_code=204)
async def remove(node_id: UUID, user: Actor, session: Session, config: Product):
    await nodes.delete_node(session, user.id, node_id, config)
    return Response(status_code=204)


@router.get(
    "/{node_id}/senses",
    response_model=SensePage | DeckSenses,
    openapi_extra={"security": [{}]},
)
async def senses(
    node_id: UUID,
    viewer: Viewer,
    session: Session,
    config: Product,
    lexicon: Dictionary,
    after_id: int = Query(default=0, ge=0),
):
    viewer_id = viewer.id if viewer else None
    node = await readable(session, node_id, viewer_id, config)
    return await sense_page(session, node, viewer_id, config, lexicon, after_id)
