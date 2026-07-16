"""Canonical subtree resolution with live-reference authorization."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.hierarchy.models import NodeType

_SUBTREE_NODES_SQL = text(
    """
    WITH RECURSIVE subtree AS (
        SELECT id, author_id, type, target_node_id
        FROM nodes
        WHERE id = :root_id AND deleted_at IS NULL
        UNION ALL
        SELECT child.id, child.author_id, child.type, child.target_node_id
        FROM nodes child
        JOIN subtree parent ON child.parent_node_id = parent.id
        WHERE child.deleted_at IS NULL AND child.author_id = parent.author_id
    )
    SELECT id, type, target_node_id FROM subtree
    """
)


async def resolve_deck_ids(
    session: AsyncSession, root_id: UUID, viewer_id: UUID | None = None
) -> list[UUID]:
    """Return direct decks plus independently readable live reference targets."""
    result = await session.execute(_SUBTREE_NODES_SQL, {"root_id": str(root_id)})
    direct_decks: set[UUID] = set()
    reference_targets: set[UUID] = set()
    for node_id, node_type, target_node_id in result:
        if node_type == NodeType.DECK:
            direct_decks.add(node_id)
        elif node_type == NodeType.REFERENCE and target_node_id is not None:
            reference_targets.add(target_node_id)

    visible_targets = await _readable_reference_targets(
        session, reference_targets, viewer_id
    )
    return list(direct_decks | visible_targets)


async def _readable_reference_targets(
    session: AsyncSession, target_ids: set[UUID], viewer_id: UUID | None
) -> set[UUID]:
    """Resolve all referenced targets and their ancestry in one recursive query.

    Calling ``session.get``/``can_read_node`` once per reference made a broad
    public folder an N+1 query path. This mirrors that visibility rule in SQL:
    the target and every ancestor must be live, and a target is readable by its
    owner, directly public, or below a same-owner public folder.
    """
    if not target_ids:
        return set()
    rows = await session.execute(
        text(
            """
            WITH RECURSIVE ancestry AS (
                SELECT id AS target_id, id, parent_node_id, author_id, type, visibility,
                       deleted_at
                FROM nodes
                WHERE id = ANY(CAST(:target_ids AS uuid[]))
                UNION ALL
                SELECT ancestry.target_id, parent.id, parent.parent_node_id,
                       parent.author_id, parent.type, parent.visibility, parent.deleted_at
                FROM nodes parent
                JOIN ancestry ON ancestry.parent_node_id = parent.id
            ), target AS (
                SELECT ancestry.target_id, target_node.author_id::text AS target_author,
                       target_node.type::text AS target_type,
                       target_node.visibility = 'PUBLIC' AS target_public,
                       bool_and(ancestry.deleted_at IS NULL) AS live_chain,
                       bool_and(ancestry.author_id = target_node.author_id) AS same_owner,
                       bool_or(
                           ancestry.type = 'FOLDER' AND ancestry.visibility = 'PUBLIC'
                       ) AS public_ancestor
                FROM ancestry
                JOIN nodes target_node ON target_node.id = ancestry.target_id
                GROUP BY ancestry.target_id, target_node.author_id,
                         target_node.type, target_node.visibility
            )
            SELECT target_id FROM target
            WHERE target_type = 'DECK' AND live_chain
              AND (
                  CAST(:viewer_id AS text) IS NULL
                  OR target_author = CAST(:viewer_id AS text)
                  OR target_public OR (same_owner AND public_ancestor)
              )
            """
        ),
        {
            "target_ids": [str(target_id) for target_id in target_ids],
            "viewer_id": str(viewer_id) if viewer_id is not None else None,
        },
    )
    return {row.target_id for row in rows}


async def resolve_sense_ids(
    session: AsyncSession, root_id: UUID, viewer_id: UUID | None = None
) -> list[int]:
    """Return the distinct canonical sense set for an authorized node scope."""
    deck_ids = await resolve_deck_ids(session, root_id, viewer_id)
    if not deck_ids:
        return []
    stmt = text(
        """
        SELECT DISTINCT sense_id FROM deck_senses
        WHERE node_id = ANY(CAST(:deck_ids AS uuid[]))
        ORDER BY sense_id
        """
    )
    result = await session.execute(stmt, {"deck_ids": [str(deck_id) for deck_id in deck_ids]})
    return [row[0] for row in result]
