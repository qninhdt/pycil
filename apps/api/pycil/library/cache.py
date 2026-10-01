"""The library tree's one cache: a deck's sense membership, fenced by generation.

Keyed ``deck:{id}:senses:v{content_generation}``. That is the whole unit. There is
deliberately no composite subtree cache and no per-viewer variant: the previous
design materialized an entire authorized subtree's senses under one key, optionally
per viewer, and maintained it by walking ancestors and inbound references on every
edit. That made one deck's content edit proportional to how many people referenced
it, and made a shared cache entry a de-facto authorization record. Both are gone.

A node or child-list cache was specified alongside it and never earned a caller:
nothing populated it, so nothing could read it, and the only code that touched those
keys was an invalidation deleting entries that were never written. The tree read goes
to PostgreSQL, which is also the authority for readability — so a visibility or
ownership change takes effect immediately rather than at the end of a TTL.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.library.models import Node, NodeType
from pycil.library.tree import ancestor_chain

#: Fenced by the deck's own generation rather than by time: a membership change bumps
#: the generation and the old key simply stops being read, so there is no staleness
#: window at all. The TTL only bounds how long an unread key occupies memory.
_LONG_TTL = 86400


def deck_senses_key(deck_id: UUID, content_generation: int) -> str:
    return f"deck:{deck_id}:senses:v{content_generation}"


# --- deck membership ---------------------------------------------------------


async def get_deck_senses(redis: Redis, deck_id: UUID, content_generation: int) -> list[int] | None:
    raw = await redis.get(deck_senses_key(deck_id, content_generation))
    return json.loads(raw) if raw else None


async def set_deck_senses(
    redis: Redis, deck_id: UUID, content_generation: int, sense_ids: Iterable[int]
) -> None:
    await redis.set(
        deck_senses_key(deck_id, content_generation),
        json.dumps(list(sense_ids)),
        ex=_LONG_TTL,
    )


async def deck_generations(session: AsyncSession, deck_ids: Collection[UUID]) -> dict[UUID, int]:
    """Current content generations for an authorized deck set.

    Read from PostgreSQL in one query rather than from the node cache: a cached
    generation would be a stale number used to choose which membership key to
    trust, which turns a display cache into a correctness input.
    """
    if not deck_ids:
        return {}
    rows = await session.execute(
        select(Node.id, Node.content_generation).where(
            Node.id.in_(deck_ids), Node.type == NodeType.DECK
        )
    )
    return {node_id: generation for node_id, generation in rows}


async def bump_deck_content_generation(session: AsyncSession, deck_id: UUID) -> int:
    """Increment one deck's generation in the caller's transaction.

    O(1) in the number of decks that reference this one: nothing outside this row
    is read or written. The old membership key is not deleted — it expires on its
    own TTL and, more importantly, nothing reads it again once the generation has
    moved. Deleting before the transaction commits would be wrong: a rollback
    would leave the cache missing a key the database still considers current.
    """
    generation = await session.scalar(
        update(Node)
        .where(Node.id == deck_id)
        .values(content_generation=Node.content_generation + 1)
        .returning(Node.content_generation)
    )
    return generation or 0


async def bump_structural_generation(session: AsyncSession, node_ids: Collection[UUID]) -> None:
    """Bump the session-scope fence for these nodes and all their ancestors.

    A study session's scope is one node — the folder or deck it was started on —
    and what that scope *contains* is its whole readable subtree. So a sense added
    to a deck three levels down changes the scope of every folder above it, and
    each of those has to move.

    This is deliberately not `bump_deck_content_generation`. The two columns fence
    different things: `content_generation` fences the cached deck membership and is
    bumped only on the deck whose senses changed, while `structural_generation`
    fences the live session scope and has to reach every ancestor whose subtree the
    change lands in. Bumping the wrong one either leaves a session serving stale
    content or invalidates sessions nothing changed.

    Runs in the caller's transaction, so a rollback leaves the fence untouched.
    The chain comes from `ancestor_chain`, which already bounds the walk by the
    collection depth cap and stops on a repeated id; the write is then one ORM
    statement so the session's own identity map moves with it. A raw UPDATE would
    bump the row and leave an already-loaded `Node` in this session reporting the
    old value, which is the one read the fence depends on.
    """
    ids: set[UUID] = set()
    for node_id in node_ids:
        if node_id is not None:
            ids.update(await ancestor_chain(session, node_id))
    if not ids:
        return
    await session.execute(
        update(Node)
        .where(Node.id.in_(ids))
        .values(structural_generation=Node.structural_generation + 1)
        .execution_options(synchronize_session="fetch")
    )
