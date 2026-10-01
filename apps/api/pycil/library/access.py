"""Set-based node readability and the collection's IDOR gate."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.schemas import CurrentUser
from pycil.library.models import Node, NodeType
from pycil.platform.errors import ForbiddenError, NotFoundError


@dataclass(frozen=True)
class ActorRef:
    """Id-only principal for callers that hold just the actor's UUID."""

    id: UUID


@dataclass(frozen=True)
class ReadabilityRow:
    """One hop in a candidate's ancestor chain."""

    candidate_id: UUID
    node_id: UUID
    depth: int
    node_type: NodeType
    readable: bool


# The recursive query also terminates on a repeated id. The cap bounds a malformed
# acyclic chain, while valid writes are checked against the same limit.
MAX_COLLECTION_DEPTH = 64


_READABILITY_SQL = text(
    """
    WITH RECURSIVE ancestry AS (
        SELECT n.id AS candidate_id,
               n.id AS node_id,
               n.parent_node_id,
               n.author_id,
               n.type,
               n.visibility,
               n.deleted_at,
               0 AS depth,
               ARRAY[n.id]::uuid[] AS path
        FROM nodes n
        WHERE n.id = ANY(CAST(:candidate_ids AS uuid[]))

        UNION ALL

        SELECT ancestry.candidate_id,
               parent.id,
               parent.parent_node_id,
               parent.author_id,
               parent.type,
               parent.visibility,
               parent.deleted_at,
               ancestry.depth + 1,
               ancestry.path || parent.id
        FROM ancestry
        JOIN nodes parent ON parent.id = ancestry.parent_node_id
        WHERE ancestry.depth < :max_depth
          AND parent.id <> ALL(ancestry.path)
    ),
    hop_verdicts AS (
        SELECT hop.candidate_id,
               hop.node_id,
               hop.depth,
               hop.type AS node_type,
               bool_and(ancestor.deleted_at IS NULL) AS live_chain,
               bool_and(ancestor.author_id = hop.author_id) AS same_owner_chain,
               bool_or(
                   ancestor.type = 'FOLDER' AND ancestor.visibility = 'PUBLIC'
               ) AS public_ancestor,
               hop.author_id::text AS node_author,
               hop.visibility = 'PUBLIC' AS node_public
        FROM ancestry hop
        JOIN ancestry ancestor
          ON ancestor.candidate_id = hop.candidate_id
         AND ancestor.depth >= hop.depth
        GROUP BY hop.candidate_id,
                 hop.node_id,
                 hop.depth,
                 hop.type,
                 hop.author_id,
                 hop.visibility
    )
    SELECT candidate_id,
           node_id,
           depth,
           node_type,
           live_chain AND (
               node_author = CAST(:viewer_id AS text)
               OR node_public
               OR (same_owner_chain AND public_ancestor)
           ) AS readable
    FROM hop_verdicts
    ORDER BY candidate_id, depth
    """
)


async def readability_rows(
    session: AsyncSession,
    candidate_ids: set[UUID] | list[UUID] | tuple[UUID, ...],
    viewer_id: UUID | None,
) -> list[ReadabilityRow]:
    """Return one readable verdict for every candidate and every ancestor hop.

    The candidate id identifies the original request, ``depth`` is zero for that
    node and increases towards the root. The same query therefore serves single
    node authorization, batch deck authorization, and breadcrumb resolution.
    Missing candidates produce no rows; callers deliberately collapse that with a
    false verdict so private and missing nodes remain indistinguishable.
    """
    ids = list(dict.fromkeys(candidate_ids))
    if not ids:
        return []
    result = await session.execute(
        _READABILITY_SQL,
        {
            "candidate_ids": [str(node_id) for node_id in ids],
            "viewer_id": str(viewer_id) if viewer_id is not None else None,
            "max_depth": MAX_COLLECTION_DEPTH,
        },
    )
    return [
        ReadabilityRow(
            candidate_id=row["candidate_id"],
            node_id=row["node_id"],
            depth=int(row["depth"]),
            node_type=NodeType(row["node_type"]),
            readable=bool(row["readable"]),
        )
        for row in result.mappings()
    ]


async def readable_node_ids(
    session: AsyncSession,
    candidate_ids: set[UUID] | list[UUID] | tuple[UUID, ...],
    viewer_id: UUID | None,
) -> set[UUID]:
    """Return readable candidates from the shared set-based query."""
    return {
        row.candidate_id
        for row in await readability_rows(session, candidate_ids, viewer_id)
        if row.depth == 0 and row.readable
    }


async def require_node_access(
    session: AsyncSession,
    node_id: UUID,
    user: CurrentUser | ActorRef | None,
    *,
    write: bool = False,
) -> Node:
    """Return a node the actor may use, collapsing private and missing reads."""
    if write:
        node = await session.get(Node, node_id)
        if node is None or node.deleted_at is not None:
            raise NotFoundError("node_not_found")
        if user is None or node.author_id != user.id:
            raise ForbiddenError("not_node_owner", code="forbidden")
        return node

    viewer_id = user.id if user is not None else None
    if node_id not in await readable_node_ids(session, [node_id], viewer_id):
        raise NotFoundError("node_not_found")
    node = await session.get(Node, node_id)
    if node is None or node.deleted_at is not None:
        raise NotFoundError("node_not_found")
    return node


async def can_read_node(session: AsyncSession, node: Node, user_id: UUID | None) -> bool:
    """Whether ``user_id`` may read ``node`` through the shared query."""
    return node.id is not None and node.id in await readable_node_ids(session, [node.id], user_id)
