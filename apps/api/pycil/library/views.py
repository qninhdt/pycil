"""Read-side helpers for the collection routes.

These are the queries and shaping steps used by the collection routes. Nothing here
is a route, and nothing here mutates. Anything that writes belongs in `service.py`;
anything that authorizes belongs in `access.py`.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.lexicon.contracts import LexiReader
from pycil.library import analytics
from pycil.library.access import readability_rows
from pycil.library.models import Node
from pycil.library.schemas import (
    HistoryBucketRead,
    NodeAncestorRead,
    WeakSenseRead,
)
from pycil.platform.errors import ConflictError
from pycil.study.engine.mastery import DailyHistoryBucket
from pycil.study.models import UserSenseStats

# Ceiling on the ids `/me/cefr` pulls into memory. That endpoint is the only
# remaining caller of `tracked_sense_ids`, because CEFR level is Lexi-side data
# that a pycil query cannot group by. Far above any real learner's tracked set, so
# in practice it truncates nothing — it exists so one pathological account cannot
# turn a request into an unbounded scan.
TRACKED_SENSE_CEILING = 20_000


async def readable_path(
    session: AsyncSession, node: Node, viewer_id: UUID | None
) -> list[NodeAncestorRead]:
    """Return a root-first readable suffix, stopping at the first hidden hop.

    ``readability_rows`` performs the policy calculation for every hop in one
    recursive query. This function only materialises names and types after the
    query has supplied ids, verdicts, and depths.
    """
    if node.id is None:
        return []
    verdicts = [row for row in await readability_rows(session, [node.id], viewer_id)]
    verdicts.sort(key=lambda row: row.depth, reverse=True)
    if not verdicts:
        return []

    rows = await session.execute(select(Node).where(Node.id.in_([row.node_id for row in verdicts])))
    by_id = {row.id: row for row in rows.scalars()}
    # Walk root-first and remember the LAST unreadable hop, then keep only what
    # sits below it. Keying off the FIRST unreadable hop leaks every private
    # ancestor stacked between it and the readable suffix — two private folders
    # above a published one would expose the middle one's name. Readability is a
    # contiguous suffix for a node the caller can open, so slicing after the last
    # hidden hop yields exactly the visible trail without dropping a readable one.
    first_visible = 0
    for index, verdict in enumerate(verdicts):
        if not verdict.readable:
            first_visible = index + 1
    return [
        NodeAncestorRead(id=hop.id, name=hop.name, type=hop.type)
        for verdict in verdicts[first_visible:]
        if (hop := by_id.get(verdict.node_id)) is not None
    ]


async def hydrate_weakest(
    client: LexiReader, weak: list[analytics.WeakSense]
) -> list[WeakSenseRead]:
    """Attach the content needed to render each weakest-sense row.

    One `get_senses` call for the whole page. Split out from `weakest_rows` so the
    global variant can select its rows with a different query while sharing this
    shape — the two must not drift.
    """
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


async def owned_children_page(
    session: AsyncSession,
    author_id: UUID,
    parent_node_id: UUID | None,
    *,
    cursor: UUID | None = None,
    limit: int = 50,
) -> tuple[list[Node], str | None]:
    """One page of children owned by the caller, ordered stably.

    Kept out of `list_nodes` so the route is only HTTP mapping. An author
    filter is essential: `list_nodes` lists roots when `parent_node_id` is None,
    and without this filter an authenticated caller receives every user's
    root folders.
    """
    stmt = (
        select(Node)
        .where(
            Node.author_id == author_id,
            Node.parent_node_id == parent_node_id,
            Node.deleted_at.is_(None),
        )
        .order_by(Node.created_at.desc(), Node.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        anchor = await session.get(Node, cursor)
        if anchor is None:
            raise ConflictError("invalid_cursor")
        stmt = stmt.where(
            (Node.created_at < anchor.created_at)
            | ((Node.created_at == anchor.created_at) & (Node.id < anchor.id))
        )
    rows = list((await session.execute(stmt)).scalars())
    next_cursor = str(rows[limit - 1].id) if len(rows) > limit else None
    return rows[:limit], next_cursor


def history_window(
    from_date: date | None, to_date: date | None, *, default_days: int = 30
) -> tuple[date, date]:
    """Validate and default the review-history date range."""
    end = to_date or datetime.now(UTC).date()
    start = from_date or (end - timedelta(days=default_days - 1))
    if start > end or (end - start).days > 365:
        raise ConflictError("history_window_invalid")
    return start, end


def history_read(buckets: list[DailyHistoryBucket]) -> list[HistoryBucketRead]:
    return [
        HistoryBucketRead(
            bucket=bucket.day.isoformat(),
            reviewed=bucket.reviewed,
            avg_mastery=bucket.avg_mastery,
        )
        for bucket in buckets
    ]


async def tracked_sense_ids(session: AsyncSession, user_id: UUID) -> list[int]:
    """All sense ids this user has an active study record for, capped."""
    stmt = (
        select(UserSenseStats.sense_id)
        .where(UserSenseStats.user_id == user_id)
        .order_by(UserSenseStats.sense_id)
        .limit(TRACKED_SENSE_CEILING)
    )
    return list((await session.execute(stmt)).scalars())
