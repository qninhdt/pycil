"""Targeted ancestry authorization and local folder/reference traversal."""

from sqlalchemy import Text, Uuid, and_, any_, cast, literal, or_, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import aliased

from pycil.http import Problem
from pycil.library.models import CollectionNode as Node
from pycil.library.models import DeckSense, NodeType, Visibility


def ancestry(seeds, max_depth):
    """Walk toward roots by PK; deleted/broken/cyclic paths never reach a root."""
    n = Node.__table__
    path = (
        select(
            n.c.id.label("seed_id"),
            n.c.id,
            n.c.owner_id,
            n.c.parent_id,
            (n.c.visibility == Visibility.PUBLIC).label("published"),
            literal(1).label("depth"),
            array([n.c.id]).label("path"),
            array([cast(n.c.name, Text)]).label("names"),
            array([n.c.visibility == Visibility.PUBLIC]).label("public_path"),
        )
        .where(n.c.id.in_(seeds), n.c.deleted_at.is_(None))
        .cte("ancestry", recursive=True, nesting=True)
    )
    parent = n.alias("ancestor")
    return path.union_all(
        select(
            path.c.seed_id,
            parent.c.id,
            parent.c.owner_id,
            parent.c.parent_id,
            or_(path.c.published, parent.c.visibility == Visibility.PUBLIC),
            path.c.depth + 1,
            path.c.path + array([parent.c.id]),
            path.c.names + array([cast(parent.c.name, Text)]),
            path.c.public_path + array([parent.c.visibility == Visibility.PUBLIC]),
        )
        .join(
            path,
            and_(
                parent.c.id == path.c.parent_id,
                parent.c.owner_id == path.c.owner_id,
                parent.c.type == NodeType.FOLDER,
            ),
        )
        .where(
            parent.c.deleted_at.is_(None),
            path.c.depth < max_depth,
            ~(parent.c.id == any_(path.c.path)),
        )
    )


def visible(node, viewer_id, max_depth):
    path = ancestry(select(node.c.id).correlate(node), max_depth)
    return (
        select(path.c.seed_id)
        .where(
            path.c.parent_id.is_(None),
            or_(path.c.owner_id == literal(viewer_id, type_=Uuid), path.c.published),
        )
        .exists()
    )


def reference_visible(node, viewer_id, max_depth):
    target = Node.__table__.alias("reference_target")
    return (
        select(target.c.id)
        .where(
            target.c.id == node.c.reference_id,
            target.c.type.in_([NodeType.FOLDER, NodeType.DECK]),
            visible(target, viewer_id, max_depth),
        )
        .correlate(node)
        .exists()
    )


def authorized_nodes(candidates, viewer_id, max_depth):
    """Authorize only supplied IDs, including current reference-target access."""
    n = Node.__table__
    path = ancestry(candidates, max_depth)
    return (
        select(*n.c, path.c.path, path.c.names, path.c.public_path)
        .join(path, path.c.seed_id == n.c.id)
        .where(
            path.c.parent_id.is_(None),
            or_(n.c.owner_id == literal(viewer_id, type_=Uuid), path.c.published),
            or_(n.c.type != NodeType.REFERENCE, reference_visible(n, viewer_id, max_depth)),
        )
        .cte("authorized_nodes", nesting=True)
    )


async def readable_path(session, node_id, viewer_id, config):
    allowed = authorized_nodes(
        select(Node.id).where(Node.id == node_id), viewer_id, config.library.max_depth
    )
    row = (
        await session.execute(
            select(aliased(Node, allowed), allowed.c.path, allowed.c.names, allowed.c.public_path)
        )
    ).one_or_none()
    if row is None:
        raise Problem(404, "node_not_found")
    return row


async def readable(session, node_id, viewer_id, config):
    return (await readable_path(session, node_id, viewer_id, config))[0]


def scope_ids(node_id, viewer_id, config):
    """Traverse only the requested node, or the viewer's own live roots.

    Folder edges inherit access. Each reference edge independently authorizes its
    target's ancestry *before* expansion, preventing private-target traversal.
    """
    n = Node.__table__
    seeds = select(n.c.id).where(
        n.c.id == node_id
        if node_id is not None
        else and_(n.c.owner_id == viewer_id, n.c.parent_id.is_(None))
    )
    roots = authorized_nodes(seeds, viewer_id, config.library.max_depth)
    walk = select(
        roots.c.id,
        roots.c.owner_id,
        roots.c.type,
        roots.c.reference_id,
        literal(1).label("depth"),
    ).cte("scope_walk", recursive=True, nesting=True)
    child = n.alias("scope_child")
    walk = walk.union(
        select(
            child.c.id,
            child.c.owner_id,
            child.c.type,
            child.c.reference_id,
            walk.c.depth + 1,
        )
        .join(
            walk,
            or_(
                and_(
                    walk.c.type == NodeType.FOLDER,
                    child.c.parent_id == walk.c.id,
                    child.c.owner_id == walk.c.owner_id,
                ),
                and_(walk.c.type == NodeType.REFERENCE, child.c.id == walk.c.reference_id),
            ),
        )
        .where(
            child.c.deleted_at.is_(None),
            walk.c.depth < config.library.max_depth,
            or_(
                walk.c.type != NodeType.REFERENCE,
                and_(
                    child.c.type.in_([NodeType.FOLDER, NodeType.DECK]),
                    visible(child, viewer_id, config.library.max_depth),
                ),
            ),
        )
    )
    return select(DeckSense.sense_id).join(walk, walk.c.id == DeckSense.deck_id).distinct()
