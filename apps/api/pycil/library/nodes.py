"""Collection mutations with service-owned shape, ownership, and cycle checks."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.library import cache
from pycil.library.access import MAX_COLLECTION_DEPTH, readable_node_ids
from pycil.library.models import Node, NodeType, Visibility
from pycil.library.tree import ancestor_chain
from pycil.platform.errors import ConflictError, NotFoundError


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
    confirm_subtree_publication: bool = False,
) -> Node:
    await _lock_nodes(session, [parent_node_id, target_node_id])
    if node_type == NodeType.FOLDER and visibility == Visibility.PUBLIC:
        if not confirm_subtree_publication:
            raise ConflictError("folder_publication_requires_confirmation")
    if node_type == NodeType.REFERENCE:
        await _validate_reference_target(session, author_id, target_node_id)
    elif target_node_id is not None:
        raise ConflictError("target_only_allowed_for_reference")
    await _validate_parent(session, author_id, parent_node_id)

    node = Node(
        author_id=author_id,
        type=node_type,
        name=name,
        parent_node_id=parent_node_id,
        target_node_id=target_node_id,
        description=description,
        visibility=visibility,
    )
    session.add(node)
    await session.flush()
    # A new node changes what every ancestor's subtree contains, so each ancestor's
    # live session scope is now stale. Its own generation moves too, because it
    # starts as a scope in its own right.
    await cache.bump_structural_generation(session, [node.id, parent_node_id])

    await session.commit()
    await session.refresh(node)
    return node


async def move_node(
    session: AsyncSession, node: Node, new_parent_id: UUID | None, *, commit: bool = True
) -> Node:
    await _lock_nodes(session, [node.id, node.parent_node_id, new_parent_id])
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    await _validate_parent(session, current.author_id, new_parent_id)
    if new_parent_id == current.id or await _is_descendant(session, new_parent_id, current.id):
        raise ConflictError("node_move_would_create_cycle")

    previous_parent_id = current.parent_node_id
    current.parent_node_id = new_parent_id
    await _validate_subtree_depth(session, current.id, new_parent_id)
    # The subtree left one scope and joined another, so both sides' ancestors are
    # stale: the old ones no longer contain it, the new ones now do.
    await cache.bump_structural_generation(session, [current.id, previous_parent_id, new_parent_id])
    await _finish(session, commit)
    await session.refresh(current)
    return current


async def soft_delete_node(session: AsyncSession, node: Node, *, commit: bool = True) -> None:
    await _lock_nodes(session, [node.id, node.parent_node_id])
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    current.deleted_at = datetime.now(UTC)
    await cache.bump_structural_generation(session, [current.id, current.parent_node_id])
    await _finish(session, commit)


async def set_visibility(
    session: AsyncSession,
    node: Node,
    visibility: Visibility,
    *,
    confirm_subtree_publication: bool = False,
    commit: bool = True,
) -> Node:
    await _lock_nodes(session, [node.id, node.parent_node_id])
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    if (
        current.type == NodeType.FOLDER
        and visibility == Visibility.PUBLIC
        and current.visibility != Visibility.PUBLIC
        and not confirm_subtree_publication
    ):
        raise ConflictError("folder_publication_requires_confirmation")
    current.visibility = visibility
    # Visibility moves the boundary of what other people's live sessions can read,
    # so every ancestor's live session scope is stale.
    await cache.bump_structural_generation(session, [current.id, current.parent_node_id])
    await _finish(session, commit)
    await session.refresh(current)
    return current


async def update_node(
    session: AsyncSession,
    node: Node,
    *,
    name: str | None = None,
    description: str | None = None,
    commit: bool = True,
) -> Node:
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    if name is not None:
        current.name = name
    if description is not None:
        current.description = description
    await _finish(session, commit)
    await session.refresh(current)
    return current


async def _finish(session: AsyncSession, commit: bool) -> None:
    if commit:
        await session.commit()
    else:
        await session.flush()


async def _lock_nodes(session: AsyncSession, node_ids: list[UUID | None]) -> None:
    """Take advisory locks in stable order to reduce deadlocks."""
    valid_ids = sorted({node_id for node_id in node_ids if node_id is not None})
    for node_id in valid_ids:
        # pg_advisory_xact_lock takes a bigint; use lower 63 bits of UUID int
        lock_id = node_id.int & 0x7FFFFFFFFFFFFFFF
        await session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})


async def _validate_parent(session: AsyncSession, author_id: UUID, parent_id: UUID | None) -> None:
    if parent_id is None:
        return
    parent = await session.get(Node, parent_id)
    if parent is None or parent.deleted_at is not None:
        raise NotFoundError("parent_not_found")
    if parent.author_id != author_id or parent.type != NodeType.FOLDER:
        raise ConflictError("parent_must_be_owned_folder")
    depth = len(await ancestor_chain(session, parent_id))
    if depth >= MAX_COLLECTION_DEPTH:
        raise ConflictError("node_depth_exceeded")


async def _validate_reference_target(
    session: AsyncSession, author_id: UUID, target_id: UUID | None
) -> None:
    if target_id is None:
        raise ConflictError("reference_requires_target")
    readable = await readable_node_ids(session, [target_id], author_id)
    if target_id not in readable:
        raise NotFoundError("reference_target_not_found")
    target = await session.get(Node, target_id)
    if target is None or target.deleted_at is not None:
        raise NotFoundError("reference_target_not_found")
    if target.type == NodeType.REFERENCE:
        raise ConflictError("reference_must_target_deck_or_folder")


async def _is_descendant(
    session: AsyncSession, candidate_id: UUID | None, ancestor_id: UUID
) -> bool:
    if candidate_id is None:
        return False
    chain = await ancestor_chain(session, candidate_id)
    return ancestor_id in chain


async def _validate_subtree_depth(
    session: AsyncSession, moving_node_id: UUID, new_parent_id: UUID | None
) -> None:
    parent_depth = len(await ancestor_chain(session, new_parent_id)) if new_parent_id else 0
    # Recursive CTE to find maximum relative depth of subtree
    stmt = text(
        """
        WITH RECURSIVE st AS (
            SELECT id, 0 AS rel_depth
            FROM nodes
            WHERE id = :node_id AND deleted_at IS NULL
            UNION ALL
            SELECT child.id, st.rel_depth + 1
            FROM nodes child
            JOIN st ON child.parent_node_id = st.id
            WHERE child.deleted_at IS NULL
        )
        SELECT COALESCE(MAX(rel_depth), 0) FROM st
        """
    )
    res = await session.scalar(stmt, {"node_id": moving_node_id})
    subtree_rel_depth = int(res or 0)
    # Total depth is parent_depth (number of ancestors) + 1 (the node itself) + subtree_rel_depth
    if parent_depth + 1 + subtree_rel_depth > MAX_COLLECTION_DEPTH:
        raise ConflictError("node_depth_exceeded")
