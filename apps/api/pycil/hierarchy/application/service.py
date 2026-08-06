"""Hierarchy mutations with service-owned shape, ownership, and cycle checks."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.common.errors import ConflictError, NotFoundError
from pycil.hierarchy.application import cache
from pycil.hierarchy.application.ancestry import ancestor_chain
from pycil.hierarchy.infra.models import DeckAttributes, Node, NodeType, Visibility


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
    if node_type == NodeType.DECK:
        session.add(DeckAttributes(node_id=node.id))

    prior = await cache.bump_generations(session, [node.id, parent_node_id])
    await session.commit()
    await session.refresh(node)
    await cache.delete_prior_defsets_quietly(prior)
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

    old_parent = current.parent_node_id
    current.parent_node_id = new_parent_id
    affected = await _descendant_ids(session, current.id)
    affected.update([old_parent, new_parent_id])
    prior = await cache.bump_generations(session, affected)
    if commit:
        await session.commit()
        await session.refresh(current)
        await cache.delete_prior_defsets_quietly(prior)
    else:
        await session.flush()
    return current


async def soft_delete_node(session: AsyncSession, node: Node, *, commit: bool = True) -> None:
    await _lock_nodes(session, [node.id, node.parent_node_id])
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    current.deleted_at = datetime.now(UTC)
    affected = await _descendant_ids(session, current.id)
    affected.add(current.parent_node_id)
    prior = await cache.bump_generations(session, affected)
    if commit:
        await session.commit()
        await cache.delete_prior_defsets_quietly(prior)
    else:
        await session.flush()


async def set_visibility(
    session: AsyncSession,
    node: Node,
    visibility: Visibility,
    *,
    confirm_subtree_publication: bool = False,
    commit: bool = True,
) -> Node:
    """Change direct visibility and invalidate all dependent live-reference sets."""
    await _lock_nodes(session, [node.id, node.parent_node_id])
    current = await session.get(Node, node.id, with_for_update=True)
    if current is None or current.deleted_at is not None:
        raise NotFoundError("node_not_found")
    if current.type == NodeType.FOLDER and visibility == Visibility.PUBLIC:
        if not confirm_subtree_publication:
            raise ConflictError("folder_publication_requires_confirmation")
    current.visibility = visibility
    affected = await _descendant_ids(session, current.id)
    affected.add(current.parent_node_id)
    prior = await cache.bump_generations(session, affected)
    if commit:
        await session.commit()
        await session.refresh(current)
        await cache.delete_prior_defsets_quietly(prior)
    else:
        await session.flush()
    return current


async def update_node(
    session: AsyncSession,
    node: Node,
    *,
    name: str | None,
    description: str | None,
) -> Node:
    """Persist editable node metadata without changing tree/cache structure."""
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


async def _validate_reference_target(
    session: AsyncSession, actor_id: UUID, target_node_id: UUID | None
) -> None:
    if target_node_id is None:
        raise ConflictError("reference_requires_target")
    target = await session.scalar(select(Node).where(Node.id == target_node_id).with_for_update())
    if target is None or target.deleted_at is not None:
        raise NotFoundError("reference_target_not_found")
    if target.type != NodeType.DECK:
        raise ConflictError("reference_must_target_deck")
    if target.author_id != actor_id and target.visibility != Visibility.PUBLIC:
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


async def _descendant_ids(session: AsyncSession, root_id: UUID) -> set[UUID | None]:
    descendants: set[UUID | None] = {root_id}
    frontier = {root_id}
    while frontier:
        rows = await session.execute(select(Node.id).where(Node.parent_node_id.in_(frontier)))
        children = set(rows.scalars()) - descendants
        descendants.update(children)
        frontier = children
    return descendants


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

