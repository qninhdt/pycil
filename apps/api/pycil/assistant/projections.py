"""Compact, batched context for the Assistant's task tools."""

from dataclasses import asdict

from lexi_ai.contract import Sense, Word
from sqlalchemy import or_, select

from pycil.http import Problem
from pycil.library.access import reference_visible, visible
from pycil.library.models import Node, NodePath, NodeRole, NodeType
from pycil.library.scope import ScopeBudget
from pycil.study.progress import summaries
from pycil.vocabulary.context import viewer_context


async def vocabulary(resources, user, config, word_ids=(), sense_ids=(), include=()):
    word_ids, sense_ids = set(word_ids), set(sense_ids)
    async with resources.sessions() as session:
        if word_ids:
            found = set((await session.scalars(select(Word.id).where(Word.id.in_(word_ids)))).all())
            if found != word_ids:
                raise Problem(404, "word_not_found")
        rows = list(
            (
                await session.execute(
                    select(Sense.id, Sense.word_id)
                    .where(or_(Sense.word_id.in_(word_ids), Sense.id.in_(sense_ids)))
                    .order_by(Sense.id)
                    .limit(config.projections.max_word_senses + 1)
                )
            ).all()
        )
        if len(rows) > config.projections.max_word_senses:
            raise Problem(422, "lexical_batch_too_large")
        identifiers = [r.id for r in rows]
        if not sense_ids <= set(identifiers):
            raise Problem(404, "sense_not_found")
        context = (
            {
                s["sense_id"]: s
                for s in (
                    await viewer_context(
                        session,
                        user.id,
                        config,
                        identifiers,
                        include_sources="sources" in include,
                        max_senses=config.projections.max_word_senses,
                    )
                )["senses"]
            }
            if identifiers and set(include) & {"learning", "sources"}
            else {}
        )
    facts = {
        s["sense_id"]: dict(s) for s in await resources.lexicon.get_sense_previews(identifiers)
    }
    native = (
        {s.id: s for s in await resources.lexicon.get_senses(identifiers)}
        if set(include) & {"examples", "lexical_details"}
        else {}
    )
    result = []
    for identifier in identifiers:
        if identifier not in facts or (
            set(include) & {"examples", "lexical_details"} and identifier not in native
        ):
            raise Problem(409, "learning_content_changed")
        item = {
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
            item["examples"] = [e.content for e in native[identifier].examples[:2]]
        if "lexical_details" in include:
            details = asdict(native[identifier])
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


def node_projection(node, user_id):
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


async def node_cards(session, user_id, config, rows):
    if not rows:
        return []
    identifiers = [r["id"] for r in rows]
    ancestor = Node.__table__.alias("ancestor")
    paths = {i: [] for i in identifiers}
    for row in (
        await session.execute(
            select(NodePath.descendant_id, ancestor.c.id, ancestor.c.name)
            .join(ancestor, ancestor.c.id == NodePath.ancestor_id)
            .where(NodePath.descendant_id.in_(identifiers), visible(ancestor, user_id))
            .order_by(NodePath.descendant_id, NodePath.depth.desc())
        )
    ).all():
        paths[row.descendant_id].append({"node_id": row.id, "name": row.name})
    available = dict(
        (
            await session.execute(
                select(Node.id, reference_visible(Node.__table__, user_id)).where(
                    Node.id.in_(identifiers), Node.type == NodeType.REFERENCE
                )
            )
        ).all()
    )
    counts = []
    size = config.learning.limits.max_summary_nodes
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
            "path": paths[row["id"]],
            "reference_available": available.get(row["id"]),
            "summary": count,
        }
        for row, count in zip(rows, counts, strict=True)
    ]


async def saved_node(resources, user_id, config, result):
    return (await saved_nodes(resources, user_id, config, [result]))[0]


async def saved_nodes(resources, user_id, config, results):
    items = []
    for result in results:
        item = node_projection(result, user_id)
        if "sense_ids" in result:
            item["sense_count"] = len(result["sense_ids"])
        for key in ("added_count", "removed_count", "retained_reference_id"):
            if key in result:
                item[key] = result[key]
        items.append(item)
    # The write already committed; enrichment failure must not report it as failed.
    async with resources.sessions() as session:
        try:
            counts = await summaries(session, user_id, config, [r["id"] for r in results])
        except Problem as exc:
            for item in items:
                item["summary_error"] = exc.code
        else:
            for item, count in zip(items, counts, strict=True):
                item["summary"] = count
    return items
