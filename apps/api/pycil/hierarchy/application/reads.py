"""Read-side helpers for the hierarchy routes.

These are the queries and shaping steps the routes call, extracted from
`router.py` so that module is routes only. All read traffic used to live inside
the router while `service.py` owned mutations, which meant reads had no layer of
their own and bypassed the service boundary entirely — a 553-line file mixing 14
routes with the SQL behind them.

Nothing here is a route, and nothing here mutates. Anything that writes belongs in
`service.py`; anything that authorizes belongs in `access.py`.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import ConflictError
from pycil.hierarchy.application import stats
from pycil.hierarchy.application.ancestry import ancestor_chain
from pycil.hierarchy.domain.schemas import (
    HistoryBucketRead,
    NodeAncestorRead,
    WeakSenseRead,
)
from pycil.hierarchy.infra.models import Node, NodeType, Visibility
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
    """Root-first breadcrumb, truncated at the first ancestor the caller cannot read.

    The whole chain is fetched once and readability is then decided in Python over
    those rows, so this costs the walk plus one SELECT rather than re-walking per
    ancestor. The rule is the same one `can_read_node` applies: the viewer owns it,
    it is public, or a same-owner public FOLDER sits above it.

    Truncation, not omission: an unreadable ancestor removes itself AND everything
    above it, so a private folder's name never reaches a caller who cannot open it.
    The node itself is always present, because `require_node_access` already
    authorized it and the `IN` fetch is unfiltered, so its row is always in `by_id`.
    Everything below depends on that — the `chain[start:]` slice, the
    `_readable(start - 1)` walk, and the "last hop needs no check" argument all
    assume `chain` ends at `node`. `ancestor_chain` upholds it even on a cyclic
    tree, because the walk starts AT the node and stops on a repeat, so the node is
    always the first element appended and therefore the last after the reverse.
    `test_breadcrumb_still_names_the_node_on_a_cyclic_tree` pins it.
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
    return [int(sense_id) for sense_id in rows.scalars()]


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
    COUNT over the same predicate.

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
    next_cursor = str(nodes[limit].id) if len(nodes) > limit else None
    return nodes[:limit], next_cursor
