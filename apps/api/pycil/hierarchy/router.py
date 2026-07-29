"""Hierarchy routes: node CRUD + folder stats. Every route ownership-gated.

require_node_access is a hard dependency on every route — owner-only write,
owner-or-public read — closing the systemic IDOR gap. Stats stay inside pycil's
DB; CEFR distribution resolves content through the LexiReader port.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user, optional_current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiReader
from pycil.db.session import get_session
from pycil.hierarchy import cache, service, stats, subtree
from pycil.hierarchy.access import require_node_access
from pycil.hierarchy.ancestry import ancestor_chain
from pycil.hierarchy.models import Node, NodeType, Visibility
from pycil.hierarchy.schemas import (
    FolderItemRead,
    FolderStatsRead,
    HistoryBucketRead,
    NodeAncestorRead,
    NodeCreate,
    NodeMove,
    NodePageRead,
    NodeRead,
    NodeUpdate,
    NodeVisibilityUpdate,
    WeakSenseRead,
)
from pycil.hierarchy.viewer_stats import get_folder_stats_for_viewer
from pycil.learning.history import MasteryObservation, daily_history
from pycil.learning.models import UserSenseStats
from pycil.learning.policy import MASTERED_FLOOR

router = APIRouter(tags=["hierarchy"])


async def _defset(session: AsyncSession, node_id: UUID, viewer_id: UUID | None) -> list[int]:
    """Read a generation-safe, viewer-scoped canonical subtree sense set."""
    for _ in range(2):
        generation = await cache.current_generation(session, node_id)
        if generation is None:
            return []
        try:
            cached = await cache.get_defset(node_id, generation, viewer_id=viewer_id)
        except Exception:
            cached = None
        if cached is not None:
            return cached
        sense_ids = await subtree.resolve_sense_ids(session, node_id, viewer_id)
        if await cache.current_generation(session, node_id) == generation:
            try:
                await cache.set_defset(
                    node_id, sense_ids, generation=generation, viewer_id=viewer_id
                )
            except Exception:
                pass
            return sense_ids
    return await subtree.resolve_sense_ids(session, node_id, viewer_id)


async def _deck_item_counts(session: AsyncSession, node_ids: list[UUID]) -> dict[UUID, int]:
    """Sense counts for the given decks in ONE grouped aggregate.

    Deliberately not `_defset`: that does two generation SELECTs, a Redis GET, and
    on a miss two recursive CTEs plus a membership SELECT, all bound to a single
    root. Looping it over a 50-row page is ~250 round trips. Folder aggregates and
    due counts are therefore not served on the list response at all — they belong
    on the opened node, where `_defset`'s cache applies.
    """
    if not node_ids:
        return {}
    rows = await session.execute(
        text(
            """
            SELECT node_id, count(*) AS items FROM deck_senses
            WHERE node_id = ANY(CAST(:node_ids AS uuid[]))
            GROUP BY node_id
            """
        ),
        {"node_ids": [str(node_id) for node_id in node_ids]},
    )
    return {row.node_id: int(row.items) for row in rows}


async def _readable_path(
    session: AsyncSession, node: Node, viewer_id: UUID | None
) -> list[NodeAncestorRead]:
    """Root-first breadcrumb, truncated at the first ancestor the caller cannot read.

    The whole chain is fetched once and readability is then decided in Python over
    those rows, so this costs the walk plus one SELECT rather than re-walking per
    ancestor. The rule is the same one `can_read_node` applies: the viewer owns it,
    it is public, or a same-owner public FOLDER sits above it.

    Truncation, not omission: an unreadable ancestor removes itself AND everything
    above it, so a private folder's name never reaches a caller who cannot open it.
    The node itself is always present, because `require_node_access` already
    authorized it.
    """
    chain_ids = await ancestor_chain(session, node.id)
    if len(chain_ids) <= 1:
        return [NodeAncestorRead(id=node.id, name=node.name, type=node.type)]
    rows = await session.execute(select(Node).where(Node.id.in_(chain_ids)))
    by_id = {row.id: row for row in rows.scalars()}
    chain = [by_id[node_id] for node_id in chain_ids if node_id in by_id]

    # Forward pass: inherited-public requires an UNBROKEN same-author run from a
    # public FOLDER down to the hop, which is what can_read_node's walk enforces by
    # bailing out the moment the author changes.
    inherited = [False] * len(chain)
    public_folder_above = False
    for index, hop in enumerate(chain):
        if index > 0:
            if hop.author_id != chain[index - 1].author_id:
                public_folder_above = False
            inherited[index] = public_folder_above
        if hop.type == NodeType.FOLDER and hop.visibility == Visibility.PUBLIC:
            public_folder_above = True

    def _readable(index: int) -> bool:
        hop = chain[index]
        return (
            (viewer_id is not None and hop.author_id == viewer_id)
            or hop.visibility == Visibility.PUBLIC
            or inherited[index]
        )

    # Keep the longest readable suffix. The last hop is the node itself, already
    # authorized by require_node_access, so the loop always terminates with it in.
    start = len(chain) - 1
    while start > 0 and _readable(start - 1):
        start -= 1
    return [
        NodeAncestorRead(id=hop.id, name=hop.name, type=hop.type) for hop in chain[start:]
    ]


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
    statement = select(Node).where(
        Node.author_id == user.id,
        Node.parent_node_id == parent_node_id,
        Node.deleted_at.is_(None),
    )
    if cursor is not None:
        statement = statement.where(Node.id > cursor)
    rows = await session.execute(statement.order_by(Node.id).limit(limit + 1))
    nodes = list(rows.scalars())
    page = nodes[:limit]
    # One grouped aggregate for the whole page, never one query per row.
    counts = await _deck_item_counts(
        session, [node.id for node in page if node.type == NodeType.DECK]
    )
    items: list[NodeRead] = []
    for node in page:
        read = NodeRead.model_validate(node)
        if node.type == NodeType.DECK:
            read.item_count = counts.get(node.id, 0)
        items.append(read)
    return NodePageRead(
        items=items,
        next_cursor=str(nodes[limit].id) if len(nodes) > limit else None,
    )


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
    read.path = await _readable_path(session, node, viewer_id)
    if node.type == NodeType.DECK:
        read.item_count = (await _deck_item_counts(session, [node.id])).get(node.id, 0)
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


async def _weakest_rows(
    session: AsyncSession,
    client: LexiReader,
    user_id: UUID,
    sense_ids: list[int],
    limit: int,
) -> list[WeakSenseRead]:
    """Weakest senses, hydrated with the content needed to render a row.

    One `get_senses` call for the whole page. Shared by the folder and global
    variants so the two cannot drift into different shapes.
    """
    weak = await stats.weakest_senses(session, user_id, sense_ids, limit=limit)
    if not weak:
        return []
    views = {
        view.sense_id: view
        for view in await client.get_senses([item.sense_id for item in weak])
        if view.sense_id is not None
    }
    rows: list[WeakSenseRead] = []
    for item in weak:
        view = views.get(item.sense_id)
        rows.append(
            WeakSenseRead(
                sense_id=item.sense_id,
                mastery=item.mastery,
                # A sense regenerated away in Lexi still has stats here, so the
                # content fields stay optional rather than dropping the row.
                word=view.word if view else None,
                definition=view.definition if view else None,
                pos=view.pos if view else None,
                cefr_level=view.cefr_level if view else None,
            )
        )
    return rows


@router.get("/folders/{node_id}/weakest", response_model=list[WeakSenseRead])
async def folder_weakest(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[WeakSenseRead]:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await _defset(session, node_id, user.id)
    return await _weakest_rows(session, client, user.id, sense_ids, limit)


@router.get("/folders/{node_id}/cefr", response_model=dict[str, int])
async def folder_cefr(
    node_id: UUID,
    user: Annotated[CurrentUser | None, Depends(optional_current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> dict[str, int]:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await _defset(session, node_id, user.id if user is not None else None)
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
        await _defset(session, node_id, user.id if user is not None else None)
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


def _history_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    """Resolve and validate a day-bucket window. Shared by folder and global reads
    so the two cannot diverge on the 365-day cap or the inverted-range rejection."""
    end = to_date or datetime.now(UTC).date()
    start = from_date or end - timedelta(days=29)
    if start > end or (end - start).days > 365:
        raise ConflictError("history_window_invalid")
    return start, end


async def _history_buckets(
    session: AsyncSession, user_id: UUID, sense_ids: list[int], start: date, end: date
) -> list[HistoryBucketRead]:
    """Day-bucketed review history over a sense set, carrying the pre-window
    baseline forward so an untouched day reports the mastery it inherited."""
    if not sense_ids:
        return [
            HistoryBucketRead(bucket=day.isoformat(), reviewed=0, avg_mastery=0.0)
            for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
        ]
    start_at = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    end_at = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    baseline_rows = await session.execute(
        text(
            """
            SELECT DISTINCT ON (sense_id) sense_id, mastery_after
            FROM review_log
            WHERE user_id = :user_id
              AND sense_id = ANY(CAST(:sense_ids AS bigint[]))
              AND reviewed_at < :start_at
            ORDER BY sense_id, reviewed_at DESC, id DESC
            """
        ),
        {"user_id": str(user_id), "sense_ids": sense_ids, "start_at": start_at},
    )
    event_rows = await session.execute(
        text(
            """
            SELECT sense_id, reviewed_at, mastery_after
            FROM review_log
            WHERE user_id = :user_id
              AND sense_id = ANY(CAST(:sense_ids AS bigint[]))
              AND reviewed_at >= :start_at AND reviewed_at < :end_at
            ORDER BY reviewed_at, id
            """
        ),
        {
            "user_id": str(user_id),
            "sense_ids": sense_ids,
            "start_at": start_at,
            "end_at": end_at,
        },
    )
    baseline = {int(row.sense_id): int(row.mastery_after) for row in baseline_rows}
    events = [
        MasteryObservation(int(row.sense_id), row.reviewed_at, int(row.mastery_after))
        for row in event_rows
    ]
    return [
        HistoryBucketRead(
            bucket=item.day.isoformat(), reviewed=item.reviewed, avg_mastery=item.avg_mastery
        )
        for item in daily_history(start, end, baseline, events)
    ]


async def _tracked_sense_ids(session: AsyncSession, user_id: UUID) -> list[int]:
    """Every sense this caller has learning state for.

    This is the global scope. Aggregating over `user_sense_stats` rows rather than
    fanning out over roots is what keeps a sense held in two decks from
    double-counting — the same reason `resolve_sense_ids` uses SELECT DISTINCT —
    and it skips subtree resolution entirely, so it is cheaper than the folder path
    rather than a sum of it.
    """
    rows = await session.execute(
        select(UserSenseStats.sense_id).where(UserSenseStats.user_id == user_id)
    )
    return [int(sense_id) for sense_id in rows.scalars()]


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
    start, end = _history_window(from_date, to_date)
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await _defset(session, node_id, user.id)
    return await _history_buckets(session, user.id, sense_ids, start, end)


@router.get("/me/stats", response_model=FolderStatsRead)
async def global_stats(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> FolderStatsRead:
    from sqlalchemy import case, func

    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((UserSenseStats.review_count > 0, 1), else_=0)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (UserSenseStats.review_count > 0)
                                & (UserSenseStats.mastery >= MASTERED_FLOOR),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.avg(UserSenseStats.mastery).filter(UserSenseStats.review_count > 0),
                    0.0,
                ),
            ).where(UserSenseStats.user_id == user.id)
        )
    ).one()
    return FolderStatsRead(
        total=int(row[0]), learned=int(row[1]), mastered=int(row[2]), avg_mastery=float(row[3])
    )


@router.get("/me/history", response_model=list[HistoryBucketRead])
async def global_history(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    bucket: Literal["day"] = "day",
) -> list[HistoryBucketRead]:
    """`folder_history` over every sense the caller has state for."""
    del bucket
    start, end = _history_window(from_date, to_date)
    sense_ids = await _tracked_sense_ids(session, user.id)
    return await _history_buckets(session, user.id, sense_ids, start, end)


@router.get("/me/cefr", response_model=dict[str, int])
async def global_cefr(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
) -> dict[str, int]:
    """`folder_cefr` over every sense the caller has state for."""
    return await stats.cefr_distribution(client, await _tracked_sense_ids(session, user.id))


@router.get("/me/weakest", response_model=list[WeakSenseRead])
async def global_weakest(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiReader = Depends(get_lexi_client),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[WeakSenseRead]:
    """`folder_weakest` over every sense the caller has state for."""
    sense_ids = await _tracked_sense_ids(session, user.id)
    return await _weakest_rows(session, client, user.id, sense_ids, limit)
