"""Hierarchy routes: node CRUD + folder stats. Every route ownership-gated.

require_node_access is a hard dependency on every route — owner-only write,
owner-or-public read — closing the systemic IDOR gap. Stats stay inside pycil's
DB; CEFR distribution resolves content through the LexiClient port.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiClient
from pycil.db.session import get_session
from pycil.hierarchy import cache, service, stats, subtree
from pycil.hierarchy.access import require_node_access
from pycil.hierarchy.schemas import (
    FolderStatsRead,
    NodeCreate,
    NodeMove,
    NodeRead,
    WeakSenseRead,
)

router = APIRouter(tags=["hierarchy"])


async def _defset(session: AsyncSession, node_id: UUID) -> list[int]:
    """L1-cached Stage-1 sense-id set for a folder/deck subtree."""
    cached = await cache.get_defset(node_id)
    if cached is not None:
        return cached
    sense_ids = await subtree.resolve_sense_ids(session, node_id)
    await cache.set_defset(node_id, sense_ids)
    return sense_ids


@router.post("/nodes", response_model=NodeRead, status_code=201)
async def create_node(
    body: NodeCreate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    # If nesting under a parent, the caller must own the parent (write access).
    if body.parent_node_id is not None:
        await require_node_access(session, body.parent_node_id, user, write=True)
    node = await service.create_node(
        session,
        user.id,
        node_type=body.type,
        name=body.name,
        parent_node_id=body.parent_node_id,
        target_node_id=body.target_node_id,
        description=body.description,
        visibility=body.visibility,
    )
    return NodeRead.model_validate(node)


@router.patch("/nodes/{node_id}/move", response_model=NodeRead)
async def move_node(
    node_id: UUID,
    body: NodeMove,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    node = await require_node_access(session, node_id, user, write=True)
    if body.parent_node_id is not None:
        await require_node_access(session, body.parent_node_id, user, write=True)
    node = await service.move_node(session, node, body.parent_node_id)
    return NodeRead.model_validate(node)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> None:
    node = await require_node_access(session, node_id, user, write=True)
    await service.soft_delete_node(session, node)


@router.get("/folders/{node_id}/stats", response_model=FolderStatsRead)
async def folder_stats(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    mastered_threshold: int = Query(default=80, ge=0, le=100),
) -> FolderStatsRead:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await _defset(session, node_id)
    s = await stats.folder_stats(
        session, user.id, sense_ids, mastered_threshold=mastered_threshold
    )
    return FolderStatsRead(
        total=s.total, learned=s.learned, mastered=s.mastered, avg_mastery=s.avg_mastery
    )


@router.get("/folders/{node_id}/weakest", response_model=list[WeakSenseRead])
async def folder_weakest(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[WeakSenseRead]:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await _defset(session, node_id)
    weak = await stats.weakest_senses(session, user.id, sense_ids, limit=limit)
    return [WeakSenseRead(sense_id=w.sense_id, mastery=w.mastery) for w in weak]


@router.get("/folders/{node_id}/cefr", response_model=dict[str, int])
async def folder_cefr(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiClient = Depends(get_lexi_client),
) -> dict[str, int]:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await _defset(session, node_id)
    return await stats.cefr_distribution(client, sense_ids)
