"""Set-based ancestor resolution used by structural writes."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.library.access import MAX_COLLECTION_DEPTH

_ANCESTOR_CHAIN_SQL = text(
    """
    WITH RECURSIVE chain AS (
        SELECT id, parent_node_id, 0 AS depth, ARRAY[id]::uuid[] AS path
        FROM nodes
        WHERE id = :node_id

        UNION ALL

        SELECT parent.id, parent.parent_node_id, chain.depth + 1, chain.path || parent.id
        FROM chain
        JOIN nodes parent ON parent.id = chain.parent_node_id
        WHERE chain.depth < :max_depth
          AND parent.id <> ALL(chain.path)
    )
    SELECT id FROM chain ORDER BY depth DESC
    """
)


async def ancestor_chain(session: AsyncSession, node_id: UUID) -> list[UUID]:
    """Return ``node_id`` and its ancestors, root first.

    The recursive query stops at a repeated id and at the collection depth cap, so
    corrupted trees degrade to the reachable chain instead of looping forever.
    """
    result = await session.execute(
        _ANCESTOR_CHAIN_SQL,
        {"node_id": str(node_id), "max_depth": MAX_COLLECTION_DEPTH},
    )
    return list(result.scalars())
