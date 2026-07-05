"""Stage-1 subtree resolution: folder → DISTINCT sense-id set (all in pycil DB).

A recursive CTE walks ``nodes.parent_node_id`` from a root folder down to its
DECK descendants. REFERENCE leaves contribute their ``target_node_id`` deck's
senses. The result is a DISTINCT ``sense_id`` set from ``deck_senses`` — never a
cross-DB JOIN (dictionary content lives in lexi-ai's separate DB).
"""

from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# Walk the tree from :root_id, following parent→child edges. DECK and REFERENCE
# nodes are leaves for sense-collection purposes; REFERENCE maps to its target
# deck. Soft-deleted nodes are excluded at every level.
_SUBTREE_DECKS_SQL = text(
    """
    WITH RECURSIVE subtree AS (
        SELECT id, type, target_node_id
        FROM nodes
        WHERE id = :root_id AND deleted_at IS NULL
        UNION ALL
        SELECT n.id, n.type, n.target_node_id
        FROM nodes n
        JOIN subtree s ON n.parent_node_id = s.id
        WHERE n.deleted_at IS NULL
    )
    -- DECK nodes contribute directly; REFERENCE nodes contribute their target.
    SELECT DISTINCT deck_id FROM (
        SELECT id AS deck_id FROM subtree WHERE type = 'DECK'
        UNION
        SELECT target_node_id AS deck_id FROM subtree
        WHERE type = 'REFERENCE' AND target_node_id IS NOT NULL
    ) decks
    """
)


async def resolve_deck_ids(session: AsyncSession, root_id: UUID) -> list[UUID]:
    """Every DECK node id under a folder (self if the root is a deck)."""
    result = await session.execute(_SUBTREE_DECKS_SQL, {"root_id": str(root_id)})
    return [row[0] for row in result]


async def resolve_sense_ids(session: AsyncSession, root_id: UUID) -> list[int]:
    """DISTINCT sense-id set for a folder/deck subtree (Stage-1 output)."""
    deck_ids = await resolve_deck_ids(session, root_id)
    if not deck_ids:
        return []
    stmt = text(
        """
        SELECT DISTINCT sense_id FROM deck_senses
        WHERE node_id IN :deck_ids
        """
    ).bindparams(bindparam("deck_ids", expanding=True))
    result = await session.execute(stmt, {"deck_ids": [str(d) for d in deck_ids]})
    return [row[0] for row in result]
