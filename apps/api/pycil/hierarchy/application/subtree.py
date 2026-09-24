"""Canonical subtree resolution with live-reference authorization."""

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.db.redis import get_redis
from pycil.hierarchy.application import cache
from pycil.hierarchy.application.access import MAX_HIERARCHY_DEPTH, readability_rows
from pycil.hierarchy.infra.models import NodeType

_SUBTREE_NODES_SQL = text(
    """
    WITH RECURSIVE subtree AS (
        SELECT id, author_id, type, target_node_id, 0 AS depth,
               ARRAY[id]::uuid[] AS path
        FROM nodes
        WHERE id = :root_id AND deleted_at IS NULL
        UNION ALL
        SELECT child.id, child.author_id, child.type, child.target_node_id,
               parent.depth + 1, parent.path || child.id
        FROM nodes child
        JOIN subtree parent ON child.parent_node_id = parent.id
        WHERE child.deleted_at IS NULL
          AND child.author_id = parent.author_id
          AND parent.depth < :max_depth
          AND child.id <> ALL(parent.path)
    )
    SELECT id, type, target_node_id FROM subtree
    """
)


async def readable_deck_ids(
    session: AsyncSession, candidate_ids: Collection[UUID], viewer_id: UUID | None
) -> set[UUID]:
    """Filter candidate ids through the canonical readability query."""
    if not candidate_ids:
        return set()
    return {
        row.candidate_id
        for row in await readability_rows(session, list(candidate_ids), viewer_id)
        if row.depth == 0 and row.readable and row.node_type == NodeType.DECK
    }


async def resolve_deck_ids(
    session: AsyncSession, root_id: UUID, viewer_id: UUID | None = None
) -> list[UUID]:
    """Every readable deck reachable from ``root_id`` through folders and references.

    A reference may target a deck or a folder, and a folder target contributes its
    whole readable subtree — that is the difference between sharing a list and sharing
    a section of a library. References may themselves sit inside a referenced folder,
    so the walk is a worklist rather than one pass: each reference target is authorized
    and then walked in turn.

    Two bounds make that safe. Every node is walked at most once, so a pair of folders
    referencing each other terminates instead of alternating forever, and the number of
    walk roots is capped at ``MAX_HIERARCHY_DEPTH`` so a chain of references cannot
    grow without limit. The parent-child walk inside each root is bounded by the same
    depth in SQL.

    ``viewer_id=None`` means an ANONYMOUS caller, not "skip authorization". Routes
    pass ``user.id if user is not None else None`` straight through, so treating
    NULL as trusted would hand every private deck to anyone signed out.
    """
    readable: set[UUID] = set()
    pending = [root_id]
    walked: set[UUID] = set()

    while pending:
        node_id = pending.pop()
        if node_id in walked or len(walked) >= MAX_HIERARCHY_DEPTH:
            continue
        walked.add(node_id)

        result = await session.execute(
            _SUBTREE_NODES_SQL,
            {"root_id": str(node_id), "max_depth": MAX_HIERARCHY_DEPTH},
        )
        decks: set[UUID] = set()
        reference_targets: set[UUID] = set()
        for found_id, node_type, target_node_id in result:
            if node_type == NodeType.DECK:
                decks.add(found_id)
            elif node_type == NodeType.REFERENCE and target_node_id is not None:
                reference_targets.add(target_node_id)

        # A reference points outside the walked subtree, so its target is authorized
        # on its own merits rather than inheriting the root's access. Direct decks use
        # the same batch query so a corrupted cross-owner edge cannot bypass it either.
        readable |= await readable_deck_ids(session, decks, viewer_id)

        # A target the viewer cannot read is skipped entirely: it contributes nothing,
        # and walking it would be the laundering path this rule exists to close.
        for target_id in reference_targets:
            if target_id in walked:
                continue
            verdict = await readability_rows(session, [target_id], viewer_id)
            if any(row.depth == 0 and row.readable for row in verdict):
                pending.append(target_id)

    return list(readable)


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
    """:func:`resolve_sense_ids` with per-deck membership caching.

    The cache unit is one deck's membership, fenced by that deck's own content
    generation. That is the whole reason a deck edit is O(1): adding a sense to
    Bob's deck bumps Bob's generation and touches nothing else, and every folder or
    reference that resolves through it simply reads the new key next time.

    The previous design cached the entire authorized subtree under one key,
    optionally per viewer, and maintained it by walking ancestors and inbound
    references. Two things were wrong with that beyond the fan-out: the cached value
    *was* the authorization decision, so a stale entry could show a viewer senses
    they had lost access to, and the viewer-keyed variants made the entry count
    scale with readers rather than with content.

    Cache failures are swallowed on read and write. Redis is an accelerator here;
    an outage must degrade latency, not correctness, and never bypass the database
    readability check that ran to produce the deck set in the first place.
    """
    deck_ids = await resolve_deck_ids(session, root_id, viewer_id)
    if not deck_ids:
        return []

    generations = await cache.deck_generations(session, deck_ids)
    redis = get_redis()

    ordered: dict[int, None] = {}
    missing: list[UUID] = []
    for deck_id in sorted(generations, key=str):
        generation = generations[deck_id]
        try:
            cached = await cache.get_deck_senses(redis, deck_id, generation)
        except Exception:
            cached = None
        if cached is None:
            missing.append(deck_id)
            continue
        for sense_id in cached:
            ordered[sense_id] = None

    if missing:
        rows = await session.execute(
            text(
                """
                SELECT node_id, sense_id FROM deck_senses
                WHERE node_id = ANY(CAST(:deck_ids AS uuid[]))
                ORDER BY node_id, sense_id
                """
            ),
            {"deck_ids": [str(deck_id) for deck_id in missing]},
        )
        by_deck: dict[UUID, list[int]] = {deck_id: [] for deck_id in missing}
        for node_id, sense_id in rows:
            by_deck[node_id].append(sense_id)
            ordered[sense_id] = None
        for deck_id, sense_ids in by_deck.items():
            try:
                await cache.set_deck_senses(redis, deck_id, generations[deck_id], sense_ids)
            except Exception:
                pass

    return sorted(ordered)
