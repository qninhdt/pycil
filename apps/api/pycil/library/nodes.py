from datetime import UTC, datetime
from uuid import uuid7

from lexi_ai import Sense
from sqlalchemy import delete, func, insert, or_, select, tuple_

from pycil.account.lifecycle import require_user, row_data
from pycil.database import transaction_lock
from pycil.http import Problem
from pycil.library.access import published, readable, readable_path, reference_visible, visible
from pycil.library.models import DeckSense, Node, NodePath, NodeRole, NodeSpace, NodeType
from pycil.library.scope import ScopeBudget
from pycil.library.tree import add_paths, delete_subtree, move_paths, roots, subtree
from pycil.logging import get_logger
from pycil.pagination import decode, encode, includes, page_limit

logger = get_logger(__name__)


async def lock_owner(session, owner_id):
    await transaction_lock(session, f"library:{owner_id}")
    await require_user(session, owner_id)


async def owned(session, node_id, owner_id, config):
    node = await readable(session, node_id, owner_id, config)
    if node.owner_id != owner_id:
        raise Problem(404, "node_not_found")
    if node.role is NodeRole.NORMAL:
        is_published = await session.scalar(
            select(published(Node.__table__)).where(Node.id == node.id)
        )
        expected = NodeSpace.PUBLISHED if is_published else NodeSpace.PERSONAL
        if node.space is not expected:
            raise Problem(409, "invalid_tree_space")
    return node


def normal(node):
    if node.role is not NodeRole.NORMAL:
        raise Problem(422, "system_node_protected")


async def default_parent(session, owner_id, parent_id):
    if parent_id is not None:
        return parent_id
    system = await roots(session, owner_id)
    return system[NodeRole.PERSONAL_ROOT].id


async def validate_parent(session, node, parent_id, config, *, creating=False):
    parent, ancestors = await readable_path(session, parent_id, node.owner_id, config)
    if (
        parent.owner_id != node.owner_id
        or parent.type is not NodeType.FOLDER
        or parent.role is NodeRole.LIBRARY_ROOT
    ):
        raise Problem(422, "invalid_parent")
    ancestor_ids = {n.id for n in ancestors}
    actual_space = (
        NodeSpace.PUBLISHED
        if any(n.role is NodeRole.PUBLISHED_ROOT for n in ancestors)
        else NodeSpace.PERSONAL
    )
    if parent.space is not actual_space:
        raise Problem(409, "invalid_tree_space")
    if node.id in ancestor_ids or node.reference_id in ancestor_ids:
        raise Problem(422, "node_cycle")
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
    if new_depth > config.library.max_depth and (creating or new_depth > old_depth):
        raise Problem(422, "node_depth_exceeded")
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
        raise Problem(422, "node_cycle")
    if creating or parent.id != node.parent_id:
        children = await session.scalar(
            select(func.count())
            .select_from(Node)
            .where(
                Node.parent_id == parent.id,
                Node.deleted_at.is_(None),
            )
        )
        if children >= config.library.max_children_per_folder:
            raise Problem(422, "quota_exceeded")
    return parent


async def check_node_quota(session, owner_id):
    count = await session.scalar(
        select(func.count())
        .select_from(Node)
        .where(
            Node.owner_id == owner_id,
            Node.deleted_at.is_(None),
            Node.role != NodeRole.LIBRARY_ROOT,
        )
    )
    return count


async def validate_publication(session, node, parent, data, *, creating=False):
    entering = parent.space is NodeSpace.PUBLISHED and (
        creating or node.space is not NodeSpace.PUBLISHED
    )
    if entering and not data.confirm_publication:
        raise Problem(409, "publication_confirmation_required")
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
        raise Problem(422, "private_reference_cannot_be_published")


async def create_node(session, owner_id, data, config):
    async with session.begin():
        await lock_owner(session, owner_id)
        if await check_node_quota(session, owner_id) >= config.library.max_owned_nodes:
            raise Problem(422, "quota_exceeded")
        values = data.model_dump(exclude={"confirm_publication", "sense_ids"})
        values["parent_id"] = await default_parent(session, owner_id, values["parent_id"])
        node = Node(id=uuid7(), owner_id=owner_id, role=NodeRole.NORMAL, **values)
        parent = await validate_parent(session, node, node.parent_id, config, creating=True)
        await validate_publication(session, node, parent, data, creating=True)
        node.space = parent.space
        if node.reference_id:
            target = await readable(session, node.reference_id, owner_id, config)
            if target.type is NodeType.REFERENCE:
                raise Problem(422, "invalid_reference_target")
        session.add(node)
        await session.flush()
        await add_paths(session, node)
        sense_ids = None
        if node.type is NodeType.DECK:
            sense_ids = await replace_membership(session, node, data.sense_ids or [], config)
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


async def move_locked(session, node, data, config):
    old_parent, old_space = node.parent_id, node.space
    parent_id = await default_parent(session, node.owner_id, data.parent_id)
    if parent_id != node.parent_id:
        parent = await validate_parent(session, node, parent_id, config)
        await validate_publication(session, node, parent, data)
        await move_paths(session, node, parent)
    retained_id = None
    if data.retain_personal_reference:
        if old_space is not NodeSpace.PERSONAL or node.space is not NodeSpace.PUBLISHED:
            raise Problem(422, "invalid_retained_reference")
        if await check_node_quota(session, node.owner_id) >= config.library.max_owned_nodes:
            raise Problem(422, "quota_exceeded")
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
        await validate_parent(session, reference, old_parent, config, creating=True)
        session.add(reference)
        await session.flush()
        await add_paths(session, reference)
        retained_id = reference.id
    return retained_id


async def patch_node(session, owner_id, node_id, data, config):
    return await update_node(session, owner_id, node_id, data, None, config)


async def update_node(session, owner_id, node_id, metadata, membership, config):
    """Apply metadata and membership together under the existing owner lock."""
    async with session.begin():
        await lock_owner(session, owner_id)
        node = await owned(session, node_id, owner_id, config)
        normal(node)
        if metadata is not None:
            for field, value in metadata.model_dump(exclude_unset=True).items():
                setattr(node, field, value)
        changes = {}
        if membership is not None:
            if node.type is not NodeType.DECK:
                raise Problem(422, "membership_is_deck_only")
            present = set(
                (
                    await session.scalars(
                        select(DeckSense.sense_id).where(DeckSense.deck_id == node.id)
                    )
                ).all()
            )
            final = (present - set(membership.remove)) | set(membership.add)
            identifiers = await replace_membership(session, node, final, config)
            changes = {
                "sense_ids": identifiers,
                "added_count": len(final - present),
                "removed_count": len(present - final),
            }
        node.updated_at = datetime.now(UTC)
        await session.flush()
        result = row_data(node) | changes
    return result


async def patch_senses(session, owner_id, node_id, data, config):
    result = await update_node(session, owner_id, node_id, None, data, config)
    return {k: v for k, v in result.items() if k not in {"added_count", "removed_count"}}


async def move_node(session, owner_id, node_id, data, config):
    async with session.begin():
        await lock_owner(session, owner_id)
        node = await owned(session, node_id, owner_id, config)
        normal(node)
        old_parent = node.parent_id
        retained_id = await move_locked(session, node, data, config)
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


async def copy_node(session, owner_id, node_id, data, config):
    async with session.begin():
        await lock_owner(session, owner_id)
        source = await owned(session, node_id, owner_id, config)
        normal(source)
        parent, ancestors = await readable_path(session, data.parent_id, owner_id, config)
        if source.id in {node.id for node in ancestors}:
            raise Problem(422, "node_cycle")
        originals = list(
            (
                await session.scalars(
                    select(Node)
                    .join(NodePath, NodePath.descendant_id == Node.id)
                    .where(NodePath.ancestor_id == source.id, Node.deleted_at.is_(None))
                    .order_by(NodePath.depth, Node.id)
                    .limit(config.library.max_owned_nodes + 1)
                )
            ).all()
        )
        if (
            len(originals) + await check_node_quota(session, owner_id)
            > config.library.max_owned_nodes
        ):
            raise Problem(422, "quota_exceeded")
        await validate_parent(session, source, data.parent_id, config, creating=True)
        await validate_publication(session, source, parent, data, creating=True)
        identifiers = {node.id: uuid7() for node in originals}
        by_id = {node.id: node for node in originals}
        paths = list(
            (
                await session.execute(
                    select(NodePath.ancestor_id, NodePath.descendant_id, NodePath.depth).where(
                        NodePath.ancestor_id.in_(identifiers),
                        NodePath.descendant_id.in_(identifiers),
                    )
                )
            ).all()
        )
        ancestor_pairs = {(a, d) for a, d, _ in paths}
        children = {}
        for original in originals:
            normal(original)
            children[original.parent_id] = children.get(original.parent_id, 0) + 1
            if original.reference_id and (original.reference_id, original.id) in ancestor_pairs:
                raise Problem(422, "node_cycle")
        if any(
            count > config.library.max_children_per_folder
            for parent_id, count in children.items()
            if parent_id in identifiers
        ):
            raise Problem(422, "quota_exceeded")
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
                raise Problem(404, "node_not_found")
            if any(n.type is NodeType.REFERENCE for n in found.values()):
                raise Problem(422, "invalid_reference_target")
        if any(
            by_id[n.reference_id].type is NodeType.REFERENCE
            for n in originals
            if n.reference_id in by_id
        ):
            raise Problem(422, "invalid_reference_target")
        members = list(
            (
                await session.execute(
                    select(DeckSense.deck_id, DeckSense.sense_id)
                    .where(DeckSense.deck_id.in_(identifiers))
                    .limit(config.library.max_owned_memberships + 1)
                )
            ).all()
        )
        sizes = {}
        for deck_id, _ in members:
            sizes[deck_id] = sizes.get(deck_id, 0) + 1
        if any(count > config.library.max_senses_per_deck for count in sizes.values()):
            raise Problem(422, "deck_sense_limit_exceeded")
        if members:
            count = await session.scalar(
                select(func.count())
                .select_from(DeckSense)
                .join(Node)
                .where(Node.owner_id == owner_id, Node.deleted_at.is_(None))
            )
            if count + len(members) > config.library.max_owned_memberships:
                raise Problem(422, "quota_exceeded")
        copies = {
            original.id: Node(
                id=identifiers[original.id],
                owner_id=owner_id,
                role=NodeRole.NORMAL,
                parent_id=data.parent_id
                if original.id == source.id
                else identifiers[original.parent_id],
                type=original.type,
                name=original.name,
                description=original.description,
                reference_id=identifiers.get(original.reference_id, original.reference_id),
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
        depths = {d: depth for a, d, depth in paths if a == source.id}
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


async def delete_node(session, owner_id, node_id, config):
    async with session.begin():
        await lock_owner(session, owner_id)
        node = await owned(session, node_id, owner_id, config)
        normal(node)
        await delete_subtree(session, node)
        logger.info(
            "library_node_deleted",
            node_id=str(node_id),
            owner_id=str(owner_id),
            node_type=node.type.value,
        )


async def list_nodes(session, viewer_id, parent_id, cursor, config, *, limit=None, include=None):
    budget = ScopeBudget(viewer_id)
    limit = page_limit(limit, config)
    enrichment = includes(include, {"summary"})
    binding = {"kind": "nodes", "viewer": str(viewer_id), "parent": str(parent_id)}
    seek, _ = decode(cursor, binding, ["time", "uuid"])
    if parent_id is None:
        if viewer_id is None:
            raise Problem(422, "parent_required")
        system = await roots(session, viewer_id)
        parent_id = system[NodeRole.LIBRARY_ROOT].id
    parent = await readable(session, parent_id, viewer_id, config)
    if parent.type is NodeType.REFERENCE:
        if not await session.scalar(
            select(reference_visible(Node.__table__, viewer_id)).where(
                Node.id == parent.id,
            )
        ):
            raise Problem(404, "reference_unavailable")
        parent = await readable(session, parent.reference_id, viewer_id, config)
    if parent.type is not NodeType.FOLDER:
        raise Problem(422, "invalid_parent")
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
    data = [row_data(n) for n in page]
    if parent.role is NodeRole.LIBRARY_ROOT:
        for item in data:
            if item["owner_id"] != viewer_id:
                item["parent_id"] = None
    if "summary" in enrichment and page:
        from pycil.study.progress import summaries

        summary = await summaries(session, viewer_id, config, [n.id for n in page], budget=budget)
        for item, counts in zip(data, summary, strict=True):
            item["summary"] = counts
    return {
        "nodes": data,
        "next_cursor": encode(binding, [page[-1].created_at, page[-1].id])
        if len(rows) > len(page)
        else None,
    }


async def replace_membership(session, node, sense_ids, config):
    """Apply the final membership set inside the owner lock."""
    present = set(
        (
            await session.scalars(select(DeckSense.sense_id).where(DeckSense.deck_id == node.id))
        ).all()
    )
    final = set(sense_ids)
    additions, removals = final - present, present - final
    if additions and len(final) > config.library.max_senses_per_deck:
        raise Problem(422, "deck_sense_limit_exceeded")
    if len(final) > len(present):
        count = await session.scalar(
            select(func.count())
            .select_from(DeckSense)
            .join(
                Node,
                Node.id == DeckSense.deck_id,
            )
            .where(Node.owner_id == node.owner_id, Node.deleted_at.is_(None))
        )
        if count + len(final) - len(present) > config.library.max_owned_memberships:
            raise Problem(422, "quota_exceeded")
    if additions:
        existing = set(
            (await session.scalars(select(Sense.id).where(Sense.id.in_(additions)))).all()
        )
        if existing != additions:
            raise Problem(422, "sense_not_found")
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


async def node_details(session, node_id, viewer_id, config):
    node, ancestors = await readable_path(session, node_id, viewer_id, config)
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
