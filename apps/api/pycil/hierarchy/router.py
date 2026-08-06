"""Hierarchy routes: node CRUD + folder stats. Every route ownership-gated.

require_node_access is a hard dependency on every route — owner-only write,
owner-or-public read — closing the systemic IDOR gap. Stats stay inside pycil's
DB; CEFR distribution resolves content through the LexiReader port.
"""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user, optional_current_user
from pycil.auth.schemas import CurrentUser
from pycil.db.session import get_session
from pycil.hierarchy.application import reads, service, stats, subtree
from pycil.hierarchy.application.access import require_node_access
from pycil.hierarchy.application.viewer_stats import get_folder_stats_for_viewer
from pycil.hierarchy.domain.schemas import (
    FolderItemRead,
    FolderStatsRead,
    HistoryBucketRead,
    NodeCreate,
    NodeMove,
    NodePageRead,
    NodeRead,
    NodeUpdate,
    NodeVisibilityUpdate,
    WeakSenseRead,
)
from pycil.hierarchy.infra.models import NodeType
from pycil.ports.lexi import LexiReader
from pycil.ports.lexi_provider import get_lexi_client

router = APIRouter(tags=["hierarchy"])

# Ceiling on the ids `/me/cefr` pulls into memory. That endpoint is the only
# remaining caller of `_tracked_sense_ids`, because CEFR level is Lexi-side data
# that a pycil query cannot group by. Far above any real learner's tracked set, so
# in practice it truncates nothing — it exists so one pathological account cannot
# turn a request into an unbounded scan.
reads.TRACKED_SENSE_CEILING = 20_000


@router.get("/nodes", response_model=NodePageRead)
async def list_nodes(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    parent_node_id: UUID | None = Query(default=None, alias="parentNodeId"),
    cursor: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> NodePageRead:
    """List the caller's roots or one owned folder's immediate children.

    Public nodes deliberately have no discovery/listing surface; a public item is
    visible only through an explicit direct link or a tree owned by its author.
    """
    if parent_node_id is not None:
        await require_node_access(session, parent_node_id, user, write=True)
    page, next_cursor = await reads.owned_children_page(
        session, user.id, parent_node_id, cursor=cursor, limit=limit
    )
    # One grouped aggregate for the whole page, never one query per row.
    counts = await stats.deck_item_counts(
        session, [node.id for node in page if node.type == NodeType.DECK]
    )
    items: list[NodeRead] = []
    for node in page:
        read = NodeRead.model_validate(node)
        if node.type == NodeType.DECK:
            read.item_count = counts.get(node.id, 0)
        items.append(read)
    return NodePageRead(items=items, next_cursor=next_cursor)


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
        confirm_subtree_publication=body.confirm_subtree_publication,
    )
    return NodeRead.model_validate(node)


@router.patch("/nodes/{node_id}", response_model=NodeRead)
async def update_node(
    node_id: UUID,
    body: NodeUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    node = await require_node_access(session, node_id, user, write=True)
    node = await service.update_node(
        session, node, name=body.name, description=body.description
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


@router.patch("/nodes/{node_id}/visibility", response_model=NodeRead)
async def update_visibility(
    node_id: UUID,
    body: NodeVisibilityUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    node = await require_node_access(session, node_id, user, write=True)
    node = await service.set_visibility(
        session,
        node,
        body.visibility,
        confirm_subtree_publication=body.confirm_subtree_publication,
    )
    return NodeRead.model_validate(node)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> None:
    node = await require_node_access(session, node_id, user, write=True)
    await service.soft_delete_node(session, node)


@router.get("/nodes/{node_id}", response_model=NodeRead)
async def get_node(
    node_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
) -> NodeRead:
    """Read a node directly; anonymous callers see public nodes only."""
    node = await require_node_access(session, node_id, user, write=False)
    read = NodeRead.model_validate(node)
    viewer_id = user.id if user is not None else None
    read.path = await reads.readable_path(session, node, viewer_id)
    if node.type == NodeType.DECK:
        read.item_count = (await stats.deck_item_counts(session, [node.id])).get(node.id, 0)
    return read


@router.get("/folders/{node_id}/stats", response_model=FolderStatsRead)
async def folder_stats(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> FolderStatsRead:
    await require_node_access(session, node_id, user, write=False)
    s = await get_folder_stats_for_viewer(session, node_id, user.id)
    return FolderStatsRead(
        total=s.total, learned=s.learned, mastered=s.mastered, avg_mastery=s.avg_mastery
    )


@router.get("/folders/{node_id}/weakest", response_model=list[WeakSenseRead])
async def folder_weakest(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[WeakSenseRead]:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await subtree.cached_sense_ids(session, node_id, user.id)
    return await reads.weakest_rows(session, client, user.id, sense_ids, limit)


@router.get("/folders/{node_id}/cefr", response_model=dict[str, int])
async def folder_cefr(
    node_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> dict[str, int]:
    await require_node_access(session, node_id, user, write=False)
    viewer_id = user.id if user is not None else None
    sense_ids = await subtree.cached_sense_ids(session, node_id, viewer_id)
    return await stats.cefr_distribution(client, sense_ids)


@router.get("/folders/{node_id}/items", response_model=list[FolderItemRead])
async def folder_items(
    node_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[FolderItemRead]:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = (
        await subtree.cached_sense_ids(session, node_id, user.id if user is not None else None)
    )[offset : offset + limit]
    views = await client.get_senses(sense_ids)
    return [
        FolderItemRead(
            sense_id=view.sense_id,
            definition=view.definition,
            tier=view.tier,
            cefr_level=view.cefr_level,
        )
        for view in views
        if view.sense_id is not None
    ]


@router.get("/folders/{node_id}/history", response_model=list[HistoryBucketRead])
async def folder_history(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    bucket: Literal["day"] = "day",
) -> list[HistoryBucketRead]:
    del bucket  # day is the only currently supported stable bucket.
    start, end = reads.history_window(from_date, to_date)
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await subtree.cached_sense_ids(session, node_id, user.id)
    return reads.history_read(await stats.history_buckets(session, user.id, sense_ids, start, end))


@router.get("/me/stats", response_model=FolderStatsRead)
async def global_stats(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> FolderStatsRead:
    """`folder_stats` over every sense the caller has state for."""
    result = await stats.tracked_stats(session, user.id)
    return FolderStatsRead(
        total=result.total,
        learned=result.learned,
        mastered=result.mastered,
        avg_mastery=result.avg_mastery,
    )


@router.get("/me/history", response_model=list[HistoryBucketRead])
async def global_history(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    bucket: Literal["day"] = "day",
) -> list[HistoryBucketRead]:
    """`folder_history` over every sense the caller has state for.

    `sense_ids=None` selects the whole tracked set inside SQL; see
    `stats.history_buckets`. Listing the ids first was an unbounded query whose result
    was sent straight back to the same database.
    """
    del bucket
    start, end = reads.history_window(from_date, to_date)
    return reads.history_read(await stats.history_buckets(session, user.id, None, start, end))


@router.get("/me/cefr", response_model=dict[str, int])
async def global_cefr(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> dict[str, int]:
    """`folder_cefr` over every sense the caller has state for."""
    return await stats.cefr_distribution(client, await reads.tracked_sense_ids(session, user.id))


@router.get("/me/weakest", response_model=list[WeakSenseRead])
async def global_weakest(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[WeakSenseRead]:
    """`folder_weakest` over every sense the caller has state for.

    Bounded in SQL rather than in Python: the global scope is every
    `user_sense_stats` row for this caller, which is the query's own `WHERE
    user_id`, so listing those ids first only to pass them straight back was a
    whole-table round trip to answer a `LIMIT 10`.
    """
    weak = await stats.weakest_tracked_senses(session, user.id, limit=limit)
    return await reads.hydrate_weakest(client, weak)
