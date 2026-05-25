"""Node CRUD routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.schemas.node import NodeCreate, NodeRead, NodeUpdate
from pycil_core.services import node_service

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[NodeRead])
async def list_root(user: UserDep, session: SessionDep) -> list[NodeRead]:
    return await node_service.list_root_nodes(session, user.id)


@router.get("/{node_id}", response_model=NodeRead)
async def get_one(node_id: UUID, user: UserDep, session: SessionDep) -> NodeRead:
    return await node_service.get_node(session, user.id, node_id)


@router.get("/{node_id}/children", response_model=list[NodeRead])
async def list_kids(
    node_id: UUID, user: UserDep, session: SessionDep
) -> list[NodeRead]:
    return await node_service.list_children(session, user.id, node_id)


@router.post("", response_model=NodeRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: NodeCreate, user: UserDep, session: SessionDep
) -> NodeRead:
    return await node_service.create_node(session, user.id, payload)


@router.patch("/{node_id}", response_model=NodeRead)
async def update(
    node_id: UUID, payload: NodeUpdate, user: UserDep, session: SessionDep
) -> NodeRead:
    return await node_service.update_node(session, user.id, node_id, payload)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    node_id: UUID, user: UserDep, session: SessionDep
) -> None:
    await node_service.delete_node(session, user.id, node_id)


@router.post("/{node_id}/star", response_model=NodeRead)
async def toggle_star(
    node_id: UUID, user: UserDep, session: SessionDep
) -> NodeRead:
    return await node_service.toggle_flag(
        session, user.id, node_id, field="is_starred"
    )


@router.post("/{node_id}/pin", response_model=NodeRead)
async def toggle_pin(
    node_id: UUID, user: UserDep, session: SessionDep
) -> NodeRead:
    return await node_service.toggle_flag(
        session, user.id, node_id, field="is_pinned"
    )
