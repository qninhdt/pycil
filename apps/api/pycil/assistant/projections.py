"""Compact, batched context for the Assistant's task tools."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.app.projections import viewer_context
from pycil.library.access import reference_visible, visible
from pycil.library.models import Node, NodePath, NodeRole, NodeType
from pycil.library.scope import ScopeBudget
from pycil.study.progress import summaries
from pycil.vocabulary.models import Sense, Word
from pycil.vocabulary.schemas import sense_adapter
from pycil.vocabulary.words import get_sense_previews, get_senses


class ProjectionsResources(Protocol):
    sessions: async_sessionmaker[AsyncSession]
    sense_cache: Any


async def vocabulary(
    resources: ProjectionsResources,
    user: UUID,
    config: AppConfig,
    word_ids: Sequence[int] = (),
    sense_ids: Sequence[int] = (),
    include: Sequence[str] = (),
) -> dict[str, list[dict[str, Any]]]:
    word_ids_set = set(word_ids)
    sense_ids_set = set(sense_ids)
    async with resources.sessions() as session:
        if word_ids_set:
            found = set(
                (await session.scalars(select(Word.id).where(Word.id.in_(word_ids_set)))).all()
            )
            if found != word_ids_set:
                raise Problem(404, "word_not_found")
        rows = list(
            (
                await session.execute(
                    select(Sense.id, Sense.word_id)
                    .where(or_(Sense.word_id.in_(word_ids_set), Sense.id.in_(sense_ids_set)))
                    .order_by(Sense.id)
                    .limit(config.product.projections.max_word_senses + 1)
                )
            ).all()
        )
        if len(rows) > config.product.projections.max_word_senses:
            raise Problem(422, "lexical_batch_too_large")
        identifiers: list[int] = [int(r[0]) for r in rows]
        if not sense_ids_set <= set(identifiers):
            raise Problem(404, "sense_not_found")
        context = (
            {
                s["sense_id"]: s
                for s in (
                    await viewer_context(
                        session,
                        user,
                        config,
                        identifiers,
                        include_sources="sources" in include,
                        max_senses=config.product.projections.max_word_senses,
                    )
                )["senses"]
            }
            if identifiers and set(include) & {"learning", "sources"}
            else {}
        )
    facts: dict[int, dict[str, Any]] = {
        int(s["sense_id"]): dict(s)
        for s in await get_sense_previews(resources.sessions, identifiers)
    }
    native = (
        {
            s.id: s
            for s in await get_senses(resources.sessions, identifiers, cache=resources.sense_cache)
        }
        if set(include) & {"examples", "lexical_details"}
        else {}
    )
    result: list[dict[str, Any]] = []
    for identifier in identifiers:
        if identifier not in facts or (
            set(include) & {"examples", "lexical_details"} and identifier not in native
        ):
            raise Problem(409, "learning_content_changed")
        item: dict[str, Any] = {
            k: facts[identifier][k]
            for k in (
                "sense_id",
                "word_id",
                "lemma",
                "pos",
                "tier",
                "definition",
                "cefr_level",
                "register",
            )
        }
        if "examples" in include:
            item["examples"] = [
                e.content
                for e in native[identifier].examples[: config.product.projections.inline_examples]
            ]
        if "lexical_details" in include:
            details = sense_adapter.dump_python(native[identifier], mode="json")
            item |= {
                k: details[k]
                for k in ("forms", "patterns", "collocations", "relations", "ipa_uk", "ipa_us")
            }
        if "learning" in include:
            item["learning"] = context[identifier]["learning"]
        if "sources" in include:
            item |= {
                "sources": context[identifier]["decks"],
                "source_count": context[identifier]["deck_count"],
                "sources_has_more": context[identifier]["decks_has_more"],
            }
        result.append(item)
    return {"senses": result}


def node_projection(node: Mapping[str, Any], user_id: UUID) -> dict[str, Any]:
    return {
        "node_id": node["id"],
        "name": node["name"],
        "type": node["type"],
        "role": node["role"],
        "description": node.get("description"),
        "parent_id": node.get("parent_id"),
        "space": node["space"],
        "editable": node["owner_id"] == user_id and node["role"] is NodeRole.NORMAL,
    }


async def node_cards(
    session: AsyncSession,
    user_id: UUID,
    config: AppConfig,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        return []
    identifiers: list[UUID] = [cast(UUID, r["id"]) for r in rows]
    ancestor = Node.__table__.alias("ancestor")
    paths: dict[UUID, list[dict[str, Any]]] = {i: [] for i in identifiers}
    for row in (
        await session.execute(
            select(NodePath.descendant_id, ancestor.c.id, ancestor.c.name)
            .join(ancestor, ancestor.c.id == NodePath.ancestor_id)
            .where(NodePath.descendant_id.in_(identifiers), visible(ancestor, user_id))
            .order_by(NodePath.descendant_id, NodePath.depth.desc())
        )
    ).all():
        paths[row[0]].append({"node_id": row[1], "name": row[2]})
    available: dict[UUID, bool | None] = dict(
        (
            await session.execute(
                select(Node.id, reference_visible(Node.__table__, user_id)).where(
                    Node.id.in_(identifiers), Node.type == NodeType.REFERENCE
                )
            )
        ).all()
    )
    counts: list[dict[str, Any]] = []
    size = config.product.study.limits.max_summary_nodes
    budget = ScopeBudget(user_id)
    for start in range(0, len(identifiers), size):
        counts.extend(
            await summaries(
                session, user_id, config, identifiers[start : start + size], budget=budget
            )
        )
    return [
        node_projection(row, user_id)
        | {
            "path": paths[cast(UUID, row["id"])],
            "reference_available": available.get(cast(UUID, row["id"])),
            "summary": count,
        }
        for row, count in zip(rows, counts, strict=True)
    ]


async def saved_node(
    resources: ProjectionsResources,
    user_id: UUID,
    config: AppConfig,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    return (await saved_nodes(resources, user_id, config, [result]))[0]


async def saved_nodes(
    resources: ProjectionsResources,
    user_id: UUID,
    config: AppConfig,
    results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for result in results:
        item = node_projection(result, user_id)
        if "sense_ids" in result:
            item["sense_count"] = len(cast(Sequence[Any], result["sense_ids"]))
        for key in ("added_count", "removed_count", "retained_reference_id"):
            if key in result:
                item[key] = result[key]
        items.append(item)
    # The write already committed; enrichment failure must not report it as failed.
    async with resources.sessions() as session:
        try:
            counts = await summaries(
                session, user_id, config, [cast(UUID, r["id"]) for r in results]
            )
        except Problem as exc:
            for item in items:
                item["summary_error"] = exc.code
        else:
            for item, count in zip(items, counts, strict=True):
                item["summary"] = count
    return items
