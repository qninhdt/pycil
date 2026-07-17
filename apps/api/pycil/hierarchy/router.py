"""Hierarchy routes: node CRUD + folder stats. Every route ownership-gated.

require_node_access is a hard dependency on every route — owner-only write,
owner-or-public read — closing the systemic IDOR gap. Stats stay inside pycil's
DB; CEFR distribution resolves content through the LexiClient port.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ConflictError
from pycil.content.deps import get_lexi_client
from pycil.content.lexi_port import LexiClient
from pycil.db.session import get_session
from pycil.hierarchy import cache, service, stats, subtree
from pycil.hierarchy.access import require_node_access
from pycil.hierarchy.schemas import (
    FolderItemRead,
    FolderStatsRead,
    HistoryBucketRead,
    NodeCreate,
    NodeMove,
    NodeRead,
    NodeVisibilityUpdate,
    WeakSenseRead,
)
from pycil.hierarchy.viewer_stats import get_folder_stats_for_viewer
from pycil.learning.history import MasteryObservation, daily_history
from pycil.learning.models import UserSenseStats

router = APIRouter(tags=["hierarchy"])


async def _defset(session: AsyncSession, node_id: UUID, viewer_id: UUID) -> list[int]:
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
    limit: int = Query(default=10, ge=1, le=100),
) -> list[WeakSenseRead]:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await _defset(session, node_id, user.id)
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
    sense_ids = await _defset(session, node_id, user.id)
    return await stats.cefr_distribution(client, sense_ids)


@router.get("/folders/{node_id}/items", response_model=list[FolderItemRead])
async def folder_items(
    node_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
    client: LexiClient = Depends(get_lexi_client),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[FolderItemRead]:
    await require_node_access(session, node_id, user, write=False)
    sense_ids = (await _defset(session, node_id, user.id))[offset : offset + limit]
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
    end = to_date or datetime.now(UTC).date()
    start = from_date or end - timedelta(days=29)
    if start > end or (end - start).days > 365:
        raise ConflictError("history_window_invalid")
    await require_node_access(session, node_id, user, write=False)
    sense_ids = await _defset(session, node_id, user.id)
    if not sense_ids:
        return [
            HistoryBucketRead(bucket=day.isoformat(), reviewed=0, avg_mastery=0.0)
            for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
        ]
    from sqlalchemy import text

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
        {"user_id": str(user.id), "sense_ids": sense_ids, "start_at": start_at},
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
            "user_id": str(user.id),
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


@router.get("/me/stats", response_model=FolderStatsRead)
async def global_stats(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> FolderStatsRead:
    from sqlalchemy import case, func, select

    row = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((UserSenseStats.review_count > 0, 1), else_=0)), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                (UserSenseStats.review_count > 0) & (UserSenseStats.mastery >= 80),
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
