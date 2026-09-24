"""Read-side helpers for the hierarchy routes.

These are the queries and shaping steps used by the hierarchy routes. Nothing here
is a route, and nothing here mutates. Anything that writes belongs in `service.py`;
anything that authorizes belongs in `access.py`.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import ConflictError
from pycil.hierarchy.application import stats
from pycil.hierarchy.application.access import readability_rows
from pycil.hierarchy.domain.schemas import (
    HistoryBucketRead,
    NodeAncestorRead,
    WeakSenseRead,
)
from pycil.hierarchy.infra.models import Node
from pycil.policy.history import DailyHistoryBucket
from pycil.policy.sense_state import UserSenseStats
from pycil.ports.lexi import LexiReader

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
    client: LexiReader, weak: list[stats.WeakSense]
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


async def weakest_rows(
    session: AsyncSession,
    client: LexiReader,
    user_id: UUID,
    sense_ids: list[int],
    limit: int,
) -> list[WeakSenseRead]:
    """Weakest senses within an explicit sense set (the folder scope)."""
    weak = await stats.weakest_senses(session, user_id, sense_ids, limit=limit)
    return await hydrate_weakest(client, weak)


def history_read(buckets: list[DailyHistoryBucket]) -> list[HistoryBucketRead]:
    """Serialise the service's day buckets. The wire uses an ISO string key."""
    return [
        HistoryBucketRead(
            bucket=item.day.isoformat(), reviewed=item.reviewed, avg_mastery=item.avg_mastery
        )
        for item in buckets
    ]


def history_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    """Resolve and validate a day-bucket window. Shared by folder and global reads
    so the two cannot diverge on the 365-day cap or the inverted-range rejection."""
    end = to_date or datetime.now(UTC).date()
    start = from_date or end - timedelta(days=29)
    if start > end or (end - start).days > 365:
        raise ConflictError("history_window_invalid")
    return start, end


async def tracked_sense_ids(session: AsyncSession, user_id: UUID) -> list[int]:
    """Every sense this caller has learning state for, up to a hard ceiling.

    This is the global scope. Aggregating over `user_sense_stats` rows rather than
    fanning out over roots is what keeps a sense held in two decks from
    double-counting — the same reason `resolve_sense_ids` uses SELECT DISTINCT —
    and it skips subtree resolution entirely, so it is cheaper than the folder path
    rather than a sum of it.

    Only `/me/cefr` still needs the ids themselves, because `cefr_level` lives in
    Lexi and cannot be reached from a pycil `GROUP BY`. `/me/history` and
    `/me/weakest` moved to SQL-side scoping and no longer call this at all.

    The LIMIT is the point: this was an unbounded `SELECT sense_id`, so a heavy
    account materialised its whole tracked set per request. `ORDER BY sense_id`
    makes the truncation deterministic rather than dependent on physical row
    order, so a distribution built from it is stable across calls.
    """
    rows = await session.execute(
        select(UserSenseStats.sense_id)
        .where(UserSenseStats.user_id == user_id)
        .order_by(UserSenseStats.sense_id)
        .limit(TRACKED_SENSE_CEILING)
    )
    return list(rows.scalars())


async def owned_children_page(
    session: AsyncSession,
    author_id: UUID,
    parent_node_id: UUID | None,
    *,
    cursor: UUID | None,
    limit: int,
) -> tuple[list[Node], str | None]:
    """One page of the caller's own nodes under ``parent_node_id``, plus a cursor.

    Keyset pagination on the primary key: `limit + 1` rows are fetched so the
    presence of the extra row answers "is there another page" without a second
    COUNT over the same predicate. The cursor is the LAST id of the returned page;
    the resume predicate `id > cursor` then continues right after it, so walking
    pages covers every row exactly once.

    Deliberately scoped to `author_id`. Public nodes have no discovery surface —
    they are reachable by direct link or through a tree their author owns, never by
    listing — so widening this predicate would create one.
    """
    statement = select(Node).where(
        Node.author_id == author_id,
        Node.parent_node_id == parent_node_id,
        Node.deleted_at.is_(None),
    )
    if cursor is not None:
        statement = statement.where(Node.id > cursor)
    rows = await session.execute(statement.order_by(Node.id).limit(limit + 1))
    nodes = list(rows.scalars())
    page, extra = nodes[:limit], nodes[limit:]
    next_cursor = str(page[-1].id) if extra and page else None
    return page, next_cursor
