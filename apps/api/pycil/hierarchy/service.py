"""Hierarchy service: node CRUD (folder/deck/reference), move, soft-delete.

REFERENCE nodes must target a DECK (never a folder) and are leaves by
construction, so the tree stays cycle-free. Structural edits bust ancestor L1
cache keys (O(depth)).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import ConflictError, NotFoundError
from pycil.hierarchy import cache
from pycil.hierarchy.models import (
    DeckAttributes,
    FolderAttributes,
    Node,
    NodeType,
    Visibility,
)


async def create_node(
    session: AsyncSession,
    author_id: UUID,
    *,
    node_type: NodeType,
    name: str,
    parent_node_id: UUID | None = None,
    target_node_id: UUID | None = None,
    description: str | None = None,
    visibility: Visibility = Visibility.PRIVATE,
) -> Node:
    if node_type == NodeType.REFERENCE:
        await _validate_reference_target(session, target_node_id)

    node = Node(
        author_id=author_id,
        type=node_type,
        name=name,
        parent_node_id=parent_node_id,
        target_node_id=target_node_id if node_type == NodeType.REFERENCE else None,
        description=description,
        visibility=visibility,
    )
    session.add(node)
    await session.flush()

    if node_type == NodeType.FOLDER:
        session.add(FolderAttributes(node_id=node.id))
    elif node_type == NodeType.DECK:
        session.add(DeckAttributes(node_id=node.id))

    await session.commit()
    await session.refresh(node)
    if parent_node_id is not None:
        await cache.bust_ancestors(session, parent_node_id)
    return node


async def move_node(session: AsyncSession, node: Node, new_parent_id: UUID | None) -> Node:
    old_parent = node.parent_node_id
    node.parent_node_id = new_parent_id
    await session.commit()
    await session.refresh(node)
    # Bust both the old and new ancestry chains.
    if old_parent is not None:
        await cache.bust_ancestors(session, old_parent)
    if new_parent_id is not None:
        await cache.bust_ancestors(session, new_parent_id)
    return node


async def soft_delete_node(session: AsyncSession, node: Node) -> None:
    node.deleted_at = datetime.now(UTC)
    await session.commit()
    if node.parent_node_id is not None:
        await cache.bust_ancestors(session, node.parent_node_id)


async def _validate_reference_target(session: AsyncSession, target_node_id: UUID | None) -> None:
    if target_node_id is None:
        raise ConflictError("reference_requires_target", code="reference_requires_target")
    target = await session.get(Node, target_node_id)
    if target is None or target.deleted_at is not None:
        raise NotFoundError("reference_target_not_found")
    if target.type != NodeType.DECK:
        # REFERENCE can only point at a DECK — keeps the tree cycle-free.
        raise ConflictError("reference_must_target_deck", code="reference_must_target_deck")
