"""Physical tree writes, called inside the owner's serialized transaction."""

from datetime import UTC, datetime
from uuid import UUID, uuid7

from sqlalchemy import delete, insert, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from pycil.infrastructure.database import transaction_lock
from pycil.library.models import Node, NodePath, NodeRole, NodeSpace, NodeType


async def roots(session: AsyncSession, owner_id: UUID) -> dict[NodeRole, Node]:
    return {
        node.role: node
        for node in (
            await session.scalars(
                select(Node).where(Node.owner_id == owner_id, Node.role != NodeRole.NORMAL)
            )
        ).all()
    }


async def provision_library(session: AsyncSession, owner_id: UUID) -> dict[NodeRole, Node]:
    """No commit: identity and all three roots are provisioned atomically."""
    await transaction_lock(session, f"library:{owner_id}")
    existing = await roots(session, owner_id)
    if existing:
        if set(existing) != {
            NodeRole.LIBRARY_ROOT,
            NodeRole.PERSONAL_ROOT,
            NodeRole.PUBLISHED_ROOT,
        }:
            raise RuntimeError("incomplete_library_roots")
        return existing
    library = Node(
        id=uuid7(),
        owner_id=owner_id,
        type=NodeType.FOLDER,
        role=NodeRole.LIBRARY_ROOT,
        space=NodeSpace.LIBRARY,
        name="Library",
    )
    session.add(library)
    await session.flush()
    await add_paths(session, library)
    for role, space, name in (
        (NodeRole.PERSONAL_ROOT, NodeSpace.PERSONAL, "Personal"),
        (NodeRole.PUBLISHED_ROOT, NodeSpace.PUBLISHED, "Published"),
    ):
        node = Node(
            id=uuid7(),
            owner_id=owner_id,
            parent_id=library.id,
            type=NodeType.FOLDER,
            role=role,
            space=space,
            name=name,
        )
        session.add(node)
        await session.flush()
        await add_paths(session, node)
    return await roots(session, owner_id)


async def add_paths(session: AsyncSession, node: Node) -> None:
    session.add(NodePath(ancestor_id=node.id, descendant_id=node.id, depth=0))
    await session.flush()
    if node.parent_id is not None:
        await session.execute(
            insert(NodePath).from_select(
                ["ancestor_id", "descendant_id", "depth"],
                select(NodePath.ancestor_id, literal(node.id), NodePath.depth + 1).where(
                    NodePath.descendant_id == node.parent_id
                ),
            )
        )


def subtree(node_id: UUID) -> Select[UUID]:
    return select(NodePath.descendant_id).where(NodePath.ancestor_id == node_id)


async def move_paths(session: AsyncSession, node: Node, parent: Node) -> None:
    descendants = subtree(node.id)
    await session.execute(
        delete(NodePath)
        .where(NodePath.descendant_id.in_(descendants), ~NodePath.ancestor_id.in_(descendants))
        .execution_options(synchronize_session=False)
    )
    above = NodePath.__table__.alias("above")
    below = NodePath.__table__.alias("below")
    await session.execute(
        insert(NodePath).from_select(
            ["ancestor_id", "descendant_id", "depth"],
            select(above.c.ancestor_id, below.c.descendant_id, above.c.depth + below.c.depth + 1)
            .select_from(above.join(below, literal(True)))
            .where(above.c.descendant_id == parent.id, below.c.ancestor_id == node.id),
        )
    )
    await session.execute(
        update(Node)
        .where(Node.id.in_(descendants))
        .values(space=parent.space)
        .execution_options(synchronize_session="fetch")
    )
    node.parent_id = parent.id
    await session.flush()


async def delete_subtree(session: AsyncSession, node: Node) -> None:
    # Materialize bounded owned IDs before deleting the closure that selects them.
    identifiers = list((await session.scalars(subtree(node.id))).all())
    now = datetime.now(UTC)
    await session.execute(
        update(Node).where(Node.id.in_(identifiers)).values(deleted_at=now, updated_at=now)
    )
    await session.execute(
        delete(NodePath)
        .where(NodePath.descendant_id.in_(identifiers))
        .execution_options(synchronize_session=False)
    )
