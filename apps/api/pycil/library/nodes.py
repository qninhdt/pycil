from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid7

from sqlalchemy import delete, func, insert, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.lifecycle import require_user
from pycil.infrastructure.database import transaction_lock
from pycil.library.access import published, readable, readable_path, reference_visible, visible
from pycil.library.config import LibraryConfig
from pycil.library.models import DeckSense, Node, NodePath, NodeRole, NodeSpace, NodeType
from pycil.library.schemas import NodeCreate, NodeDestination, NodeMove, NodePatch, SenseDelta
from pycil.library.scope import ScopeBudget
from pycil.library.tree import add_paths, delete_subtree, move_paths, roots, subtree
from pycil.library.types import NodePageDict
from pycil.observability import get_logger
from pycil.study.config import StudyConfig
from pycil.utils.errors import Conflict, InvalidInput, NotFound
from pycil.utils.orm import row_data
from pycil.utils.pagination import (
    CursorFieldType,
    InvalidCursorError,
    SeekValue,
    decode_cursor,
    encode_cursor,
)
from pycil.vocabulary.models import Sense

logger = get_logger(__name__)


def encode(
    binding: str | Mapping[str, object],
    seek: Sequence[object],
    *,
    as_of: datetime | str | None = None,
) -> str:
    return encode_cursor(binding, seek, as_of=as_of)


def decode(
    token: str | None,
    binding: str | Mapping[str, object],
    types: Sequence[CursorFieldType],
    *,
    timed: bool = False,
) -> tuple[list[SeekValue] | None, datetime | None]:
    try:
        return decode_cursor(token, binding, types, timed=timed)
    except InvalidCursorError:
        raise InvalidInput("invalid_cursor") from None


def page_limit(limit: int | None, config: LibraryConfig) -> int:
    resolved = config.page_size if limit is None else limit
    if resolved < 1 or resolved > config.max_page_size:
        raise InvalidInput("invalid_limit")
    return resolved


def includes(value: str | None, allowed: Collection[str]) -> set[str]:
    selected: set[str] = set(value.split(",")) if value else set()
    if not selected <= set(allowed):
        raise InvalidInput("invalid_include")
    return selected


async def lock_owner(session: AsyncSession, owner_id: UUID) -> None:
    await transaction_lock(session, f"library:{owner_id}")
    await require_user(session, owner_id)


async def owned(session: AsyncSession, node_id: UUID, owner_id: UUID) -> Node:
    node = await readable(session, node_id, owner_id)
    if node.owner_id != owner_id:
        raise NotFound("node_not_found")
    if node.role is NodeRole.NORMAL:
        is_published = await session.scalar(
            select(published(Node.__table__)).where(Node.id == node.id)
        )
        expected = NodeSpace.PUBLISHED if is_published else NodeSpace.PERSONAL
        if node.space is not expected:
            raise Conflict("invalid_tree_space")
    return node


def normal(node: Node) -> None:
    if node.role is not NodeRole.NORMAL:
        raise InvalidInput("system_node_protected")


async def default_parent(session: AsyncSession, owner_id: UUID, parent_id: UUID | None) -> UUID:
    if parent_id is not None:
        return parent_id
    system = await roots(session, owner_id)
    return system[NodeRole.PERSONAL_ROOT].id


async def validate_parent(
    session: AsyncSession,
    node: Node,
    parent_id: UUID,
    config: LibraryConfig,
    *,
    creating: bool = False,
) -> Node:
    quotas = config
    parent, ancestors = await readable_path(session, parent_id, node.owner_id)
    if (
        parent.owner_id != node.owner_id
        or parent.type is not NodeType.FOLDER
        or parent.role is NodeRole.LIBRARY_ROOT
    ):
        raise InvalidInput("invalid_parent")
    ancestor_ids = {n.id for n in ancestors}
    actual_space = (
        NodeSpace.PUBLISHED
        if any(n.role is NodeRole.PUBLISHED_ROOT for n in ancestors)
        else NodeSpace.PERSONAL
    )
    if parent.space is not actual_space:
        raise Conflict("invalid_tree_space")
    if node.id in ancestor_ids or node.reference_id in ancestor_ids:
        raise InvalidInput("node_cycle")
    height = (
        await session.scalar(
            select(func.max(NodePath.depth)).where(
                NodePath.ancestor_id == node.id,
            )
        )
        or 0
    )
    library_id = ancestors[0].id
    new_depth = len(ancestors) + height
    old_depth = (
        await session.scalar(
            select(func.max(NodePath.depth)).where(
                NodePath.ancestor_id == library_id,
                NodePath.descendant_id.in_(subtree(node.id)),
            )
        )
        or 0
    )
    if new_depth > quotas.max_depth and (creating or new_depth > old_depth):
        raise InvalidInput("node_depth_exceeded")
    # A descendant reference may become a direct ancestor-reference after this move.
    invalid = await session.scalar(
        select(Node.id)
        .where(
            Node.id.in_(subtree(node.id)),
            Node.reference_id.in_(ancestor_ids),
        )
        .limit(1)
    )
    if invalid:
        raise InvalidInput("node_cycle")
    if creating or parent.id != node.parent_id:
        children = (
            await session.scalar(
                select(func.count())
                .select_from(Node)
                .where(
                    Node.parent_id == parent.id,
                    Node.deleted_at.is_(None),
                )
            )
            or 0
        )
        if children >= quotas.max_children_per_folder:
            raise InvalidInput("quota_exceeded")
    return parent


async def check_node_quota(session: AsyncSession, owner_id: UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Node)
        .where(
            Node.owner_id == owner_id,
            Node.deleted_at.is_(None),
            Node.role != NodeRole.LIBRARY_ROOT,
        )
    )
    return count or 0


async def validate_publication(
    session: AsyncSession,
    node: Node,
    parent: Node,
    data: NodeDestination | NodeCreate,
    *,
    creating: bool = False,
) -> None:
    entering = parent.space is NodeSpace.PUBLISHED and (
        creating or node.space is not NodeSpace.PUBLISHED
    )
    if entering and not data.confirm_publication:
        raise Conflict("publication_confirmation_required")
    if not entering:
        return
    references = list(
        (
            await session.scalars(
                select(Node).where(
                    Node.id.in_(subtree(node.id)),
                    Node.type == NodeType.REFERENCE,
                )
            )
        ).all()
    )
    if creating and node.type is NodeType.REFERENCE:
        references.append(node)
    targets = {n.reference_id for n in references}
    if not targets:
        return
    # Targets inside the same canonical moved subtree will become published atomically.
    allowed = set(
        (
            await session.scalars(
                select(Node.id).where(
                    Node.id.in_(targets),
                    Node.deleted_at.is_(None),
                    Node.type.in_([NodeType.FOLDER, NodeType.DECK]),
                    or_(published(Node.__table__), Node.id.in_(subtree(node.id))),
                )
            )
        ).all()
    )
    if targets != allowed:
        raise InvalidInput("private_reference_cannot_be_published")


async def create_node(
    session: AsyncSession, owner_id: UUID, data: NodeCreate, config: LibraryConfig
) -> dict[str, object]:
    quotas = config
    async with session.begin():
        await lock_owner(session, owner_id)
        if await check_node_quota(session, owner_id) >= quotas.max_owned_nodes:
            raise InvalidInput("quota_exceeded")
        values = data.model_dump(exclude={"confirm_publication", "sense_ids"})
        parent_id = await default_parent(session, owner_id, values["parent_id"])
        values["parent_id"] = parent_id
        node = Node(id=uuid7(), owner_id=owner_id, role=NodeRole.NORMAL, **values)
        parent = await validate_parent(session, node, parent_id, quotas, creating=True)
        await validate_publication(session, node, parent, data, creating=True)
        node.space = parent.space
        if node.reference_id:
            target = await readable(session, node.reference_id, owner_id)
            if target.type is NodeType.REFERENCE:
                raise InvalidInput("invalid_reference_target")
        session.add(node)
        await session.flush()
        await add_paths(session, node)
        sense_ids = None
        if node.type is NodeType.DECK:
            sense_ids = await replace_membership(session, node, data.sense_ids or [], quotas)
        result = row_data(node)
        if sense_ids is not None:
            result["sense_ids"] = sense_ids
        logger.info(
            "library_node_created",
            node_id=str(node.id),
            owner_id=str(owner_id),
            parent_id=str(node.parent_id),
            type=node.type.value,
            space=node.space.value,
            name=node.name,
        )
    return result


async def move_locked(
    session: AsyncSession, node: Node, data: NodeMove, config: LibraryConfig
) -> UUID | None:
    quotas = config
    old_parent, old_space = node.parent_id, node.space
    parent_id = await default_parent(session, node.owner_id, data.parent_id)
    if parent_id != node.parent_id:
        parent = await validate_parent(session, node, parent_id, quotas)
        await validate_publication(session, node, parent, data)
        await move_paths(session, node, parent)
    retained_id = None
    if data.retain_personal_reference:
        if old_space is not NodeSpace.PERSONAL or node.space is not NodeSpace.PUBLISHED:
            raise InvalidInput("invalid_retained_reference")
        if old_parent is None:
            raise InvalidInput("invalid_parent")
        if await check_node_quota(session, node.owner_id) >= quotas.max_owned_nodes:
            raise InvalidInput("quota_exceeded")
        reference = Node(
            id=uuid7(),
            owner_id=node.owner_id,
            parent_id=old_parent,
            type=NodeType.REFERENCE,
            role=NodeRole.NORMAL,
            space=NodeSpace.PERSONAL,
            name=node.name,
            description=node.description,
            reference_id=node.reference_id or node.id,
        )
        await validate_parent(session, reference, old_parent, quotas, creating=True)
        session.add(reference)
        await session.flush()
        await add_paths(session, reference)
        retained_id = reference.id
    return retained_id


async def patch_node(
    session: AsyncSession, owner_id: UUID, node_id: UUID, data: NodePatch, config: LibraryConfig
) -> dict[str, object]:
    return await update_node(session, owner_id, node_id, data, None, config)


async def update_node(
    session: AsyncSession,
    owner_id: UUID,
    node_id: UUID,
    metadata: NodePatch | None,
    membership: SenseDelta | None,
    config: LibraryConfig,
) -> dict[str, object]:
    """Apply metadata and membership together under the existing owner lock."""
    quotas = config
    async with session.begin():
        await lock_owner(session, owner_id)
        node = await owned(session, node_id, owner_id)
        normal(node)
        if metadata is not None:
            for field, value in metadata.model_dump(exclude_unset=True).items():
                setattr(node, field, value)
        changes: dict[str, object] = {}
        if membership is not None:
            if node.type is not NodeType.DECK:
                raise InvalidInput("membership_is_deck_only")
            present = set(
                (
                    await session.scalars(
                        select(DeckSense.sense_id).where(DeckSense.deck_id == node.id)
                    )
                ).all()
            )
            final = (present - set(membership.remove)) | set(membership.add)
            identifiers = await replace_membership(session, node, final, quotas)
            changes = {
                "sense_ids": identifiers,
                "added_count": len(final - present),
                "removed_count": len(present - final),
            }
        node.updated_at = datetime.now(UTC)
        await session.flush()
        result = row_data(node) | changes
    return result


async def patch_senses(
    session: AsyncSession, owner_id: UUID, node_id: UUID, data: SenseDelta, config: LibraryConfig
) -> dict[str, object]:
    result = await update_node(session, owner_id, node_id, None, data, config)
    return {k: v for k, v in result.items() if k not in {"added_count", "removed_count"}}


async def move_node(
    session: AsyncSession, owner_id: UUID, node_id: UUID, data: NodeMove, config: LibraryConfig
) -> dict[str, object]:
    quotas = config
    async with session.begin():
        await lock_owner(session, owner_id)
        node = await owned(session, node_id, owner_id)
        normal(node)
        old_parent = node.parent_id
        retained_id = await move_locked(session, node, data, quotas)
        node.updated_at = datetime.now(UTC)
        await session.flush()
        result = row_data(node) | {"retained_reference_id": retained_id}
        logger.info(
            "library_node_moved",
            node_id=str(node.id),
            owner_id=str(owner_id),
            old_parent_id=str(old_parent),
            new_parent_id=str(node.parent_id),
        )
    return result


async def copy_node(
    session: AsyncSession,
    owner_id: UUID,
    node_id: UUID,
    data: NodeDestination,
    config: LibraryConfig,
) -> dict[str, object]:
    quotas = config
    async with session.begin():
        await lock_owner(session, owner_id)
        source = await owned(session, node_id, owner_id)
        normal(source)
        parent, ancestors = await readable_path(session, data.parent_id, owner_id)
        if source.id in {node.id for node in ancestors}:
            raise InvalidInput("node_cycle")
        originals = list(
            (
                await session.scalars(
                    select(Node)
                    .join(NodePath, NodePath.descendant_id == Node.id)
                    .where(NodePath.ancestor_id == source.id, Node.deleted_at.is_(None))
                    .order_by(NodePath.depth, Node.id)
                    .limit(quotas.max_owned_nodes + 1)
                )
            ).all()
        )
        if len(originals) + await check_node_quota(session, owner_id) > quotas.max_owned_nodes:
            raise InvalidInput("quota_exceeded")
        await validate_parent(session, source, data.parent_id, quotas, creating=True)
        await validate_publication(session, source, parent, data, creating=True)
        identifiers = {node.id: uuid7() for node in originals}
        by_id = {node.id: node for node in originals}
        paths: list[tuple[UUID, UUID, int]] = [
            (row[0], row[1], int(row[2]))
            for row in (
                await session.execute(
                    select(NodePath.ancestor_id, NodePath.descendant_id, NodePath.depth).where(
                        NodePath.ancestor_id.in_(identifiers),
                        NodePath.descendant_id.in_(identifiers),
                    )
                )
            ).all()
        ]
        ancestor_pairs = {(a, d) for a, d, _ in paths}
        children: dict[UUID | None, int] = {}
        for original in originals:
            normal(original)
            children[original.parent_id] = children.get(original.parent_id, 0) + 1
            if original.reference_id and (original.reference_id, original.id) in ancestor_pairs:
                raise InvalidInput("node_cycle")
        if any(
            count > quotas.max_children_per_folder
            for parent_id, count in children.items()
            if parent_id in identifiers
        ):
            raise InvalidInput("quota_exceeded")
        targets = {
            n.reference_id
            for n in originals
            if n.reference_id and n.reference_id not in identifiers
        }
        if targets:
            found = {
                n.id: n
                for n in (
                    await session.scalars(
                        select(Node).where(Node.id.in_(targets), visible(Node.__table__, owner_id))
                    )
                ).all()
            }
            if set(found) != targets:
                raise NotFound("node_not_found")
            if any(n.type is NodeType.REFERENCE for n in found.values()):
                raise InvalidInput("invalid_reference_target")
        if any(
            n.reference_id is not None
            and n.reference_id in by_id
            and by_id[n.reference_id].type is NodeType.REFERENCE
            for n in originals
        ):
            raise InvalidInput("invalid_reference_target")
        members: list[tuple[UUID, int]] = [
            (row[0], int(row[1]))
            for row in (
                await session.execute(
                    select(DeckSense.deck_id, DeckSense.sense_id)
                    .where(DeckSense.deck_id.in_(identifiers))
                    .limit(quotas.max_owned_memberships + 1)
                )
            ).all()
        ]
        sizes: dict[UUID, int] = {}
        for deck_id, _ in members:
            sizes[deck_id] = sizes.get(deck_id, 0) + 1
        if any(count > quotas.max_senses_per_deck for count in sizes.values()):
            raise InvalidInput("deck_sense_limit_exceeded")
        if members:
            count = (
                await session.scalar(
                    select(func.count())
                    .select_from(DeckSense)
                    .join(Node)
                    .where(Node.owner_id == owner_id, Node.deleted_at.is_(None))
                )
                or 0
            )
            if count + len(members) > quotas.max_owned_memberships:
                raise InvalidInput("quota_exceeded")
        copies = {
            original.id: Node(
                id=identifiers[original.id],
                owner_id=owner_id,
                role=NodeRole.NORMAL,
                parent_id=data.parent_id
                if original.id == source.id
                else identifiers[cast(UUID, original.parent_id)],
                type=original.type,
                name=original.name,
                description=original.description,
                reference_id=identifiers.get(original.reference_id, original.reference_id)
                if original.reference_id is not None
                else None,
                space=parent.space,
            )
            for original in originals
        }
        # Publish targets before references; all other copy reads/writes are batched.
        for reference in (False, True):
            session.add_all(
                n for n in copies.values() if (n.type is NodeType.REFERENCE) == reference
            )
            await session.flush()
        depths: dict[UUID, int] = {d: depth for a, d, depth in paths if a == source.id}
        await session.execute(
            insert(NodePath),
            [
                {"ancestor_id": identifiers[a], "descendant_id": identifiers[d], "depth": depth}
                for a, d, depth in paths
            ]
            + [
                {
                    "ancestor_id": ancestor.id,
                    "descendant_id": identifiers[d],
                    "depth": len(ancestors) - index + depth,
                }
                for index, ancestor in enumerate(ancestors)
                for d, depth in depths.items()
            ],
        )
        if members:
            await session.execute(
                insert(DeckSense),
                [{"deck_id": identifiers[d], "sense_id": sense} for d, sense in members],
            )
        root = copies[source.id]
        result = row_data(root)
        if root.type is NodeType.DECK:
            result["sense_ids"] = sorted(sense for d, sense in members if d == source.id)
        logger.info(
            "library_node_copied",
            source_node_id=str(source.id),
            new_node_id=str(root.id),
            owner_id=str(owner_id),
            copied_node_count=len(originals),
            copied_membership_count=len(members),
        )
    return result


async def delete_node(session: AsyncSession, owner_id: UUID, node_id: UUID) -> None:
    async with session.begin():
        await lock_owner(session, owner_id)
        node = await owned(session, node_id, owner_id)
        normal(node)
        await delete_subtree(session, node)
        logger.info(
            "library_node_deleted",
            node_id=str(node_id),
            owner_id=str(owner_id),
            node_type=node.type.value,
        )


async def list_nodes(
    session: AsyncSession,
    viewer_id: UUID | None,
    parent_id: UUID | None,
    cursor: str | None,
    config: LibraryConfig,
    *,
    limit: int | None = None,
    include: str | None = None,
    study_config: StudyConfig | None = None,
) -> NodePageDict:
    budget = ScopeBudget(viewer_id)
    limit = page_limit(limit, config)
    enrichment = includes(include, {"summary"})
    binding = {"kind": "nodes", "viewer": str(viewer_id), "parent": str(parent_id)}
    seek, _ = decode(cursor, binding, ["time", "uuid"])
    if parent_id is None:
        if viewer_id is None:
            raise InvalidInput("parent_required")
        system = await roots(session, viewer_id)
        parent_id = system[NodeRole.LIBRARY_ROOT].id
    parent = await readable(session, parent_id, viewer_id)
    if parent.type is NodeType.REFERENCE:
        if not await session.scalar(
            select(reference_visible(Node.__table__, viewer_id)).where(
                Node.id == parent.id,
            )
        ):
            raise NotFound("reference_unavailable")
        assert parent.reference_id is not None
        parent = await readable(session, parent.reference_id, viewer_id)
    if parent.type is not NodeType.FOLDER:
        raise InvalidInput("invalid_parent")
    statement = select(Node).where(
        Node.parent_id == parent.id,
        Node.owner_id == parent.owner_id,
        Node.deleted_at.is_(None),
    )
    if parent.owner_id != viewer_id:
        statement = statement.where(
            or_(
                Node.type != NodeType.REFERENCE,
                reference_visible(Node.__table__, viewer_id),
            )
        )
    if seek is not None:
        statement = statement.where(tuple_(Node.created_at, Node.id) > tuple_(*seek))
    rows = list(
        (await session.scalars(statement.order_by(Node.created_at, Node.id).limit(limit + 1))).all()
    )
    page = rows[:limit]
    data: list[dict[str, object]] = [row_data(n) for n in page]
    if parent.role is NodeRole.LIBRARY_ROOT:
        for item in data:
            if item["owner_id"] != viewer_id:
                item["parent_id"] = None
    if "summary" in enrichment and page:
        if study_config is None:
            raise InvalidInput("study_config_required")
        from pycil.study.progress import summaries

        summary = await summaries(
            session,
            viewer_id,
            study_config,
            [n.id for n in page],
            budget=budget,
            library_config=config,
        )
        for item, counts in zip(data, summary, strict=True):
            item["summary"] = counts
    return {
        "nodes": data,
        "next_cursor": encode(binding, [page[-1].created_at, page[-1].id])
        if len(rows) > len(page)
        else None,
    }


async def replace_membership(
    session: AsyncSession,
    node: Node,
    sense_ids: Sequence[int] | set[int],
    config: LibraryConfig,
) -> list[int]:
    """Apply the final membership set inside the owner lock."""
    quotas = config
    present = set(
        (
            await session.scalars(select(DeckSense.sense_id).where(DeckSense.deck_id == node.id))
        ).all()
    )
    final = set(sense_ids)
    additions, removals = final - present, present - final
    if additions and len(final) > quotas.max_senses_per_deck:
        raise InvalidInput("deck_sense_limit_exceeded")
    if len(final) > len(present):
        count = (
            await session.scalar(
                select(func.count())
                .select_from(DeckSense)
                .join(
                    Node,
                    Node.id == DeckSense.deck_id,
                )
                .where(Node.owner_id == node.owner_id, Node.deleted_at.is_(None))
            )
            or 0
        )
        if count + len(final) - len(present) > quotas.max_owned_memberships:
            raise InvalidInput("quota_exceeded")
    if additions:
        existing = set(
            (await session.scalars(select(Sense.id).where(Sense.id.in_(additions)))).all()
        )
        if existing != additions:
            raise InvalidInput("sense_not_found")
        session.add_all(DeckSense(deck_id=node.id, sense_id=s) for s in additions)
    if removals:
        await session.execute(
            delete(DeckSense).where(
                DeckSense.deck_id == node.id,
                DeckSense.sense_id.in_(removals),
            )
        )
    await session.flush()
    logger.info(
        "library_deck_senses_modified",
        deck_id=str(node.id),
        owner_id=str(node.owner_id),
        added_count=len(additions),
        removed_count=len(removals),
        total_count=len(final),
    )
    return sorted(final)


async def node_details(
    session: AsyncSession, node_id: UUID, viewer_id: UUID | None
) -> dict[str, object]:
    node, ancestors = await readable_path(session, node_id, viewer_id)
    data = row_data(node)
    if node.parent_id not in {n.id for n in ancestors}:
        data["parent_id"] = None
    available = None
    if node.type is NodeType.REFERENCE:
        available = bool(
            await session.scalar(
                select(reference_visible(Node.__table__, viewer_id)).where(
                    Node.id == node.id,
                )
            )
        )
        if not available:
            data["reference_id"] = None
    return data | {
        "breadcrumbs": [{"id": n.id, "name": n.name} for n in ancestors],
        "reference_available": available,
    }
