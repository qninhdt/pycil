"""Hierarchy mutations with service-owned shape, ownership, and cycle checks."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import ConflictError, NotFoundError
from pycil.hierarchy.application.access import MAX_HIERARCHY_DEPTH, readable_node_ids
from pycil.hierarchy.application.ancestry import ancestor_chain
from pycil.hierarchy.infra.models import Node, NodeType, Visibility


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

    await session.commit()
    await session.refresh(node)
    # Only this node and its direct parent changed shape. No ancestor walk and no
    # inbound-reference scan: nothing above or beside them depends on this edge.
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

    current.parent_node_id = new_parent_id
    await _validate_subtree_depth(session, current.id, new_parent_id)
    await _finish(session, commit)
    await session.refresh(current)
    return current


async def soft_delete_node(
    session: AsyncSession, node: Node, *, commit: bool = True
) -> None:
    await _lock_nodes(session, [node.id, node.parent_node_id])
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    current.deleted_at = datetime.now(UTC)
    await _finish(session, commit)


async def set_visibility(
    session: AsyncSession,
    node: Node,
    visibility: Visibility,
    *,
    confirm_subtree_publication: bool = False,
    commit: bool = True,
) -> Node:
    """Change a node's direct visibility."""
    await _lock_nodes(session, [node.id, node.parent_node_id])
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    if current.type == NodeType.FOLDER and visibility == Visibility.PUBLIC:
        if not confirm_subtree_publication:
            raise ConflictError("folder_publication_requires_confirmation")
    current.visibility = visibility
    await _finish(session, commit)
    await session.refresh(current)
    return current


async def _finish(session: AsyncSession, commit: bool) -> None:
    """End one mutation: commit when the caller owns the transaction, else flush.

    The assistant's approved writes open their own session and commit once at the
    end, so a mutation it calls must be able to leave the transaction open. Every
    other caller owns its request's transaction and wants the commit. Same contract
    the content service already offers, rather than a second convention.
    """
    if commit:
        await session.commit()
    else:
        await session.flush()


async def update_node(
    session: AsyncSession,
    node: Node,
    *,
    name: str | None,
    description: str | None,
) -> Node:
    """Persist editable node metadata. Name and description are not tree structure."""
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    if name is not None:
        current.name = name
    if description is not None:
        current.description = description
    await session.commit()
    await session.refresh(current)
    return current


async def _validate_parent(
    session: AsyncSession, author_id: UUID, parent_node_id: UUID | None
) -> None:
    if parent_node_id is None:
        return
    parent = await session.scalar(select(Node).where(Node.id == parent_node_id).with_for_update())
    if parent is None or parent.deleted_at is not None:
        raise NotFoundError("parent_node_not_found")
    if parent.author_id != author_id or parent.type != NodeType.FOLDER:
        raise ConflictError("parent_must_be_owned_folder")
    if len(await ancestor_chain(session, parent.id)) >= MAX_HIERARCHY_DEPTH:
        raise ConflictError("node_depth_exceeded")


async def _validate_subtree_depth(
    session: AsyncSession, root_id: UUID, new_parent_id: UUID | None
) -> None:
    """Reject moves that place any descendant beyond the hierarchy depth cap."""
    if new_parent_id is None:
        return
    parent_depth = len(await ancestor_chain(session, new_parent_id))
    result = await session.execute(
        text(
            """
            WITH RECURSIVE descendants AS (
                SELECT id, 0 AS depth, ARRAY[id]::uuid[] AS path
                FROM nodes
                WHERE id = :root_id
                UNION ALL
                SELECT child.id, descendants.depth + 1, descendants.path || child.id
                FROM descendants
                JOIN nodes child ON child.parent_node_id = descendants.id
                WHERE descendants.depth < :max_depth
                  AND child.id <> ALL(descendants.path)
            )
            SELECT COALESCE(MAX(depth), 0) FROM descendants
            """
        ),
        {"root_id": str(root_id), "max_depth": MAX_HIERARCHY_DEPTH},
    )
    subtree_height = int(result.scalar_one())
    if parent_depth + subtree_height > MAX_HIERARCHY_DEPTH:
        raise ConflictError("node_depth_exceeded")


async def _validate_reference_target(
    session: AsyncSession, actor_id: UUID, target_node_id: UUID | None
) -> None:
    """Refuse a reference the caller could not read for themselves.

    The rule is exactly "whatever you can read, you may point at" — the same
    readability query every read route uses, rather than a second, narrower check.
    A narrower one is how a deck inherited-public through its owner's published folder
    becomes readable but unreferenceable: the two rules disagree, and the caller gets a
    404 for content they are looking at.
    """
    if target_node_id is None:
        raise ConflictError("reference_requires_target")
    target = await session.scalar(select(Node).where(Node.id == target_node_id))
    if target is None or target.deleted_at is not None:
        raise NotFoundError("reference_target_not_found")
    if target.type not in (NodeType.DECK, NodeType.FOLDER):
        # A reference to another reference would be an indirection the resolver
        # cannot bound, and a reference to itself is meaningless.
        raise ConflictError("reference_must_target_deck_or_folder")
    if target_node_id not in await readable_node_ids(session, [target_node_id], actor_id):
        raise NotFoundError("reference_target_not_found")


async def _is_descendant(
    session: AsyncSession, candidate_id: UUID | None, ancestor_id: UUID
) -> bool:
    """Whether ``ancestor_id`` is ``candidate_id`` itself or one of its ancestors.

    Used for move-cycle detection, so it shares the one upward walk rather than
    keeping a fourth copy with its own cycle policy.
    """
    if candidate_id is None:
        return False
    return ancestor_id in await ancestor_chain(session, candidate_id)


def _advisory_key(node_id: UUID) -> int:
    """A 64-bit advisory-lock key taken straight from the UUID.

    `hashtext()` returns `integer`, so it folded a 128-bit UUID into 32 bits and
    two unrelated nodes collided roughly once per 65k pairs (birthday bound) —
    every collision serialising two mutations that touch nothing in common. Postgres
    advisory locks are keyed by `bigint`, so half the UUID fits natively and no hash
    is needed.

    Signed, because `pg_advisory_xact_lock` takes a signed `bigint`: the top 64 bits
    are reinterpreted as two's complement rather than shifted, which keeps the
    mapping injective. Correctness never depended on the key anyway — the unique
    constraints do — so this only widens the space and removes needless contention.
    """
    return int.from_bytes(node_id.bytes[:8], "big", signed=True)


async def _lock_nodes(session: AsyncSession, node_ids: list[UUID | None]) -> None:
    for node_id in sorted({node_id for node_id in node_ids if node_id is not None}, key=str):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:node_key)"),
            {"node_key": _advisory_key(node_id)},
        )
