"""The one upward walk of the node tree.

``subtree.py`` descends; this ascends. Three copies of the ascent existed before
(generation bumping, move-cycle detection, and the breadcrumb path this module was
extracted for), each free to disagree about cycle handling.

Cycle policy is deliberately non-raising: a node already seen terminates the walk
and the partial chain is returned. The generation-bump path runs inside structural
mutations and the breadcrumb path runs on every node read, so a corrupted tree must
degrade rather than 500.

``access.py`` keeps its own two walks. They are not duplicates of this one: they
need whole ``Node`` rows and make a per-hop authorization decision that stops early,
whereas this returns the full chain of ids and lets the caller decide.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.hierarchy.infra.models import Node


async def ancestor_chain(session: AsyncSession, node_id: UUID) -> list[UUID]:
    """Return ``node_id`` and its ancestors, ROOT FIRST.

    The node itself is the last element, so the result reads as a breadcrumb. A
    root node yields a single-element list. Terminates on a repeat rather than
    raising; see the module docstring.
    """
    chain: list[UUID] = []
    seen: set[UUID] = set()
    current: UUID | None = node_id
    while current is not None and current not in seen:
        seen.add(current)
        chain.append(current)
        current = (
            await session.execute(select(Node.parent_node_id).where(Node.id == current))
        ).scalar_one_or_none()
    chain.reverse()
    return chain
