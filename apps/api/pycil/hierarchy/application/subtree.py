"""Canonical subtree resolution with live-reference authorization."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.hierarchy.application import cache
from pycil.hierarchy.infra.models import NodeType

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

# The single SQL expression of the deck read-visibility rule, and the SQL mirror
# of ``access.can_read_node``. Any surface that has to authorize a deck it did not
# reach through ``require_node_access`` consumes this and does not write its own
# copy: three hand-written versions of this predicate is three chances to
# over-grant, and each of the three clauses below closes a specific one.
#
# - ``live_chain``    the deck and every ancestor must be undeleted. ``delete_node``
#                     is a SOFT delete, so without this a deleted deck stays
#                     world-readable forever, and a deck under a deleted folder
#                     stays readable after a share is revoked.
# - ``same_owner`` +  a public FOLDER grants inherited read only down same-owner
#   ``public_ancestor`` edges, which is what makes inherited-public and REFERENCE
#                     targets resolve the same way here as in the Python walk.
#
# ``ancestry`` seeds with the candidate itself, so the candidate's own
# ``deleted_at`` is included in ``live_chain``.
#
# An anonymous caller (NULL ``viewer_id``) is NOT special-cased. It falls through
# to ``target_public OR (same_owner AND public_ancestor)`` — the same two paths
# ``can_read_node`` allows it — because ``target_author = NULL`` evaluates to NULL
# and is filtered out. A ``viewer_id IS NULL`` disjunct here would short-circuit
# the whole condition to TRUE and hand every private deck to anyone signed out.
_READABLE_DECKS_SQL = text(
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
          target_author = CAST(:viewer_id AS text)
          OR target_public OR (same_owner AND public_ancestor)
      )
    """
)


async def readable_deck_ids(
    session: AsyncSession, candidate_ids: Collection[UUID], viewer_id: UUID | None
) -> set[UUID]:
    """Filter ``candidate_ids`` down to the live DECKs ``viewer_id`` may read.

    One recursive query for the whole candidate set, so a broad public folder or a
    sense held in many decks stays a single round trip. A candidate that is not a
    DECK, is soft-deleted, sits under a deleted ancestor, or is not visible to the
    viewer is simply absent from the result.
    """
    if not candidate_ids:
        return set()
    rows = await session.execute(
        _READABLE_DECKS_SQL,
        {
            "target_ids": [str(candidate_id) for candidate_id in candidate_ids],
            "viewer_id": str(viewer_id) if viewer_id is not None else None,
        },
    )
    return {row.target_id for row in rows}


async def resolve_deck_ids(
    session: AsyncSession, root_id: UUID, viewer_id: UUID | None = None
) -> list[UUID]:
    """Return direct decks plus independently readable live reference targets.

    ``viewer_id=None`` means an ANONYMOUS caller, not "skip authorization". Routes
    pass ``user.id if user is not None else None`` straight through, so treating
    NULL as trusted would hand every private deck to anyone signed out.
    """
    result = await session.execute(_SUBTREE_NODES_SQL, {"root_id": str(root_id)})
    direct_decks: set[UUID] = set()
    reference_targets: set[UUID] = set()
    for node_id, node_type, target_node_id in result:
        if node_type == NodeType.DECK:
            direct_decks.add(node_id)
        elif node_type == NodeType.REFERENCE and target_node_id is not None:
            reference_targets.add(target_node_id)

    # A reference points outside the walked subtree, so its target is authorized
    # on its own merits rather than inheriting the root's access.
    visible_targets = await readable_deck_ids(session, reference_targets, viewer_id)
    return list(direct_decks | visible_targets)


async def resolve_sense_ids(
    session: AsyncSession, root_id: UUID, viewer_id: UUID | None = None
) -> list[int]:
    """Return the distinct canonical sense set for an authorized node scope.

    ``viewer_id=None`` means an ANONYMOUS caller. See ``resolve_deck_ids``.
    """
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


async def cached_sense_ids(
    session: AsyncSession, root_id: UUID, viewer_id: UUID | None = None
) -> list[int]:
    """:func:`resolve_sense_ids` behind the generation-fenced cache.

    The single home for this read. It existed as two byte-identical 22-line copies
    — one private to `router.py`, one private to `viewer_stats.py` — and the logic
    it duplicates is subtle enough that divergence would not be obvious: the
    generation is re-read AFTER resolving and the result is only cached when it
    still matches, so a mutation racing the resolve cannot publish a stale set
    under a fresh generation number.

    Retried twice. Each attempt can lose that race, and giving up after two falls
    through to an uncached resolve, which is always correct and merely slower —
    preferable to looping against a node being mutated repeatedly.

    Cache failures are swallowed on both read and write. Redis is an accelerator
    here, not a source of truth; an outage must degrade latency, not answers.
    """
    for _ in range(2):
        generation = await cache.current_generation(session, root_id)
        if generation is None:
            return []
        try:
            cached = await cache.get_defset(root_id, generation, viewer_id=viewer_id)
        except Exception:
            cached = None
        if cached is not None:
            return cached
        sense_ids = await resolve_sense_ids(session, root_id, viewer_id)
        if await cache.current_generation(session, root_id) == generation:
            try:
                await cache.set_defset(
                    root_id, sense_ids, generation=generation, viewer_id=viewer_id
                )
            except Exception:
                pass
            return sense_ids
    return await resolve_sense_ids(session, root_id, viewer_id)
