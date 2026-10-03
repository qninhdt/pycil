from datetime import UTC, datetime
from uuid import uuid7

from lexi_ai import Sense
from sqlalchemy import delete, func, literal, or_, select, tuple_

from pycil.account.lifecycle import require_user, row_data
from pycil.database import transaction_lock
from pycil.http import Problem
from pycil.library.access import readable, readable_path, reference_visible
from pycil.library.models import CollectionNode as Node
from pycil.library.models import DeckSense, NodeType, Visibility
from pycil.library.schemas import DeckSnapshot


async def lock_owner(session, owner_id):
    await transaction_lock(session, f"library:{owner_id}")
    await require_user(session, owner_id)


async def owned(session, node_id, owner_id):
    node = await session.get(Node, node_id)
    if node is None or node.owner_id != owner_id or node.deleted_at is not None:
        raise Problem(404, "node_not_found")
    return node


async def validate_parent(session, node, parent_id, config):
    path = []
    parent_depth = 0
    if parent_id is not None:
        parent, path, _, _ = await readable_path(session, parent_id, node.owner_id, config)
        if parent.owner_id != node.owner_id or parent.type is not NodeType.FOLDER:
            raise Problem(422, "invalid_parent")
        parent_depth = len(path)
        if node.id in path or node.reference_id in path:
            raise Problem(422, "collection_cycle")
    # Account for the whole moved subtree, not just its root.
    descendants = (
        select(Node.id, literal(1).label("depth"))
        .where(Node.id == node.id, Node.deleted_at.is_(None))
        .cte("descendants", recursive=True)
    )
    descendants = descendants.union_all(
        select(Node.id, descendants.c.depth + 1)
        .join(descendants, Node.parent_id == descendants.c.id)
        .where(
            Node.owner_id == node.owner_id,
            Node.deleted_at.is_(None),
            descendants.c.depth <= config.library.max_depth,
        )
    )
    height = await session.scalar(select(func.max(descendants.c.depth))) or 1
    if parent_depth + height > config.library.max_depth:
        raise Problem(422, "collection_depth_exceeded")


async def create_node(session, owner_id, data, config):
    async with session.begin():
        await lock_owner(session, owner_id)
        if data.visibility is Visibility.PUBLIC and not data.confirm_publication:
            raise Problem(409, "publication_confirmation_required")
        node = Node(
            id=uuid7(),
            owner_id=owner_id,
            **data.model_dump(exclude={"confirm_publication", "sense_ids"}),
        )
        await validate_parent(session, node, node.parent_id, config)
        if node.reference_id:
            target = await readable(session, node.reference_id, owner_id, config)
            if target.type is NodeType.REFERENCE:
                raise Problem(422, "invalid_reference_target")
        session.add(node)
        await session.flush()
        sense_ids = None
        if node.type is NodeType.DECK:
            sense_ids = await replace_membership(session, node, data.sense_ids or [], config)
        result = row_data(node)
        if sense_ids is not None:
            result["sense_ids"] = sense_ids
    return result


async def save_node(session, owner_id, node_id, data, config):
    async with session.begin():
        await lock_owner(session, owner_id)
        node = await owned(session, node_id, owner_id)
        await readable(session, node_id, owner_id, config)
        values = data.model_dump(exclude={"confirm_publication", "sense_ids"})
        if (
            values.get("visibility") is Visibility.PUBLIC
            and node.visibility is not Visibility.PUBLIC
            and not data.confirm_publication
        ):
            raise Problem(409, "publication_confirmation_required")
        if values["parent_id"] != node.parent_id:
            await validate_parent(session, node, values["parent_id"], config)
        sense_ids = None
        if node.type is NodeType.DECK:
            if data.sense_ids is None:
                raise Problem(422, "deck_membership_required")
            sense_ids = await replace_membership(session, node, data.sense_ids, config)
        elif data.sense_ids is not None:
            raise Problem(422, "membership_is_deck_only")
        for key, value in values.items():
            setattr(node, key, value)
        node.updated_at = datetime.now(UTC)
        await session.flush()
        result = row_data(node)
        if sense_ids is not None:
            result["sense_ids"] = sense_ids
    await invalidate_deck(session, node)
    return result


async def delete_node(session, owner_id, node_id, config):
    async with session.begin():
        await lock_owner(session, owner_id)
        node = await owned(session, node_id, owner_id)
        node.deleted_at = node.updated_at = datetime.now(UTC)
    await invalidate_deck(session, node)


async def list_nodes(session, viewer_id, parent_id, after_id, config):
    statement = select(Node).where(Node.parent_id == parent_id, Node.deleted_at.is_(None))
    if parent_id is not None:
        parent = await readable(session, parent_id, viewer_id, config)
        if parent.type is not NodeType.FOLDER:
            raise Problem(422, "invalid_parent")
        statement = statement.where(Node.owner_id == parent.owner_id)
    else:
        statement = statement.where(
            or_(Node.owner_id == viewer_id, Node.visibility == Visibility.PUBLIC)
        )
    statement = statement.where(
        or_(
            Node.type != NodeType.REFERENCE,
            reference_visible(Node.__table__, viewer_id, config.library.max_depth),
        )
    )
    if after_id is not None:
        cursor = await readable(session, after_id, viewer_id, config)
        if cursor.parent_id != parent_id:
            raise Problem(422, "invalid_cursor")
        statement = statement.where(
            tuple_(Node.created_at, Node.id) > tuple_(cursor.created_at, cursor.id)
        )
    rows = (
        await session.scalars(
            statement.order_by(Node.created_at, Node.id).limit(config.library.page_size + 1)
        )
    ).all()
    page = rows[: config.library.page_size]
    return {
        "nodes": [row_data(n) for n in page],
        "next_after_id": page[-1].id if len(rows) > len(page) else None,
    }


async def replace_membership(session, node, sense_ids, config):
    """Final state diff inside the already serialized editor transaction."""
    present = set(
        (
            await session.scalars(select(DeckSense.sense_id).where(DeckSense.deck_id == node.id))
        ).all()
    )
    final = set(sense_ids)
    additions, removals = final - present, present - final
    if additions and len(final) > config.library.max_senses_per_deck:
        raise Problem(422, "deck_sense_limit_exceeded")
    if additions:
        existing = set(
            (await session.scalars(select(Sense.id).where(Sense.id.in_(additions)))).all()
        )
        if existing != additions:
            raise Problem(422, "sense_not_found")
        session.add_all(DeckSense(deck_id=node.id, sense_id=s) for s in additions)
    if removals:
        await session.execute(
            delete(DeckSense).where(DeckSense.deck_id == node.id, DeckSense.sense_id.in_(removals))
        )
    await session.flush()
    return sorted(final)


async def invalidate_deck(session, node):
    if node.type is NodeType.DECK and (cache := session.info.get("cache")):
        await cache.discard(f"deck:{node.id}")


async def deck_snapshot(session, node):
    """Caller must perform live access checks before using this shared value."""
    cache = session.info.get("cache")
    key = f"deck:{node.id}"
    if cache and (snapshot := await cache.get(key, DeckSnapshot)) is not None:
        return snapshot
    identifiers = (
        await session.scalars(
            select(DeckSense.sense_id)
            .where(DeckSense.deck_id == node.id)
            .order_by(DeckSense.sense_id)
        )
    ).all()
    snapshot = DeckSnapshot(
        **{
            field: getattr(node, field)
            for field in DeckSnapshot.model_fields
            if field != "sense_ids"
        },
        sense_ids=list(identifiers),
    )
    if cache:
        await cache.put(key, snapshot, cache.policy.deck_ttl_seconds)
    return snapshot


async def node_details(session, node_id, viewer_id, config, lexicon):
    from pycil.library.senses import member_ids, sense_page

    node, path, names, published = await readable_path(session, node_id, viewer_id, config)
    breadcrumbs = []
    visible = node.owner_id == viewer_id
    for identifier, name, public in zip(
        reversed(path), reversed(names), reversed(published), strict=True
    ):
        visible = visible or public
        if visible:
            breadcrumbs.append({"id": identifier, "name": name})
    data = row_data(node)
    if node.parent_id not in {crumb["id"] for crumb in breadcrumbs}:
        data["parent_id"] = None
    result = data | {"breadcrumbs": breadcrumbs}
    if node.type is NodeType.DECK:
        snapshot = await deck_snapshot(session, node)
        result["sense_count"] = len(snapshot.sense_ids)
        result.update(
            await sense_page(session, node, viewer_id, config, lexicon, snapshot=snapshot)
        )
    else:
        result["sense_count"] = await session.scalar(
            select(func.count()).select_from(member_ids(node, viewer_id, config).subquery())
        )
    return result
