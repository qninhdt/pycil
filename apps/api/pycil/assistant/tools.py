"""Task-oriented tools over the same authorized product services as HTTP."""

import asyncio
import json
from dataclasses import asdict
from functools import wraps

from fastapi.encoders import jsonable_encoder
from langchain_core.tools import ToolException, tool
from lexi_ai.errors import InvalidResourceError
from pydantic import ValidationError

from pycil.account.api import patch_settings, profile
from pycil.account.schemas import PreferencesPatch
from pycil.assistant.projections import (
    node_cards,
    node_projection,
    saved_node,
    saved_nodes,
    vocabulary,
)
from pycil.assistant.schemas import (
    GenerationRead,
    LearningOverview,
    LibraryRead,
    NodeBatch,
    NodeCopy,
    NodeMove,
    NodeSearch,
    NodeUpdate,
    VocabularyRead,
    WordGeneration,
    WordSearch,
)
from pycil.http import Problem
from pycil.library import nodes
from pycil.library.access import readable
from pycil.library.models import NodeRole, NodeType
from pycil.library.schemas import NodeCreate, NodeDestination, NodePatch, SenseDelta
from pycil.library.schemas import NodeMove as Move
from pycil.library.scope import ScopeBudget
from pycil.library.search import search_nodes as search_service
from pycil.library.senses import sense_page
from pycil.library.tree import roots
from pycil.logging import get_logger
from pycil.study.progress import activity, schedules, summaries

logger = get_logger(__name__)

MUTATION_TOOLS = {
    "create_node",
    "update_node",
    "move_nodes",
    "copy_nodes",
    "delete_nodes",
    "generate_words",
    "update_preferences",
}


def validation_message(error):
    return json.dumps(
        {
            "error": "invalid_tool_arguments",
            "details": error.errors(include_input=False, include_context=False, include_url=False),
        },
        separators=(",", ":"),
    )


def task_tool(schema=None):
    """Keep native tool results JSON-safe and validation feedback actionable."""

    def decorate(function):
        @wraps(function)
        async def invoke(**values):
            try:
                return jsonable_encoder(await function(**values))
            except ValidationError as error:
                raise ToolException(validation_message(error)) from None

        result = tool(args_schema=schema)(invoke)
        result.handle_tool_error = True
        result.handle_validation_error = validation_message
        return result

    return decorate


def tools(resources, user, config):
    @task_tool(WordSearch)
    async def search_words(**values):
        """Search existing Words for up to 10 terms. Limit is per query; hits include all
        sense IDs/definitions. Use generate_words for missing words. Optional include adds examples,
        lexical_details, personal learning or containing decks. Search is lexical, not semantic.
        """
        data = WordSearch(**values)
        queries = list(dict.fromkeys(data.queries))

        async def search(query):
            try:
                return (await resources.lexicon.search(query)).items
            except InvalidResourceError:
                raise Problem(422, "invalid_lexical_query") from None

        pages = await asyncio.gather(*(search(q) for q in queries))
        merged, unmatched = {}, []
        for query, hits in zip(queries, pages, strict=True):
            if not hits:
                unmatched.append(query)
            for hit in hits[: data.limit]:
                item = asdict(hit)
                identity = item["word_id"]
                merged.setdefault(identity, item | {"matched_queries": []})[
                    "matched_queries"
                ].append(query)
        word_ids = [item["word_id"] for item in merged.values()]
        senses = (
            (await vocabulary(resources, user, config, word_ids=word_ids, include=data.include))[
                "senses"
            ]
            if word_ids
            else []
        )
        groups = {}
        for sense in senses:
            groups.setdefault(sense["word_id"], []).append(sense)
        for item in merged.values():
            item["senses"] = groups.get(item["word_id"], [])
        return {"items": list(merged.values()), "unmatched_queries": unmatched}

    @task_tool(VocabularyRead)
    async def read_vocabulary(**values):
        """Read known Word/sense IDs in one batch. Returns deduplicated sense definitions;
        include examples, lexical_details, learning or sources only when needed. Word IDs and
        sense IDs are different identifiers.
        """
        data = VocabularyRead(**values)
        return await vocabulary(
            resources, user, config, data.word_ids, data.sense_ids, data.include
        )

    @task_tool(NodeSearch)
    async def search_nodes(**values):
        """Find folders/decks by multiple names. LIBRARY defaults to the user's whole
        Library, or restricts to node_id; PUBLISHED searches public Discovery. Limit is per
        query. Returns one merged list with safe paths, editability and exact summaries.
        """
        data = NodeSearch(**values)
        merged, unmatched = {}, []
        budget = ScopeBudget(user.id)
        async with resources.sessions() as session:
            root = data.node_id
            if data.scope == "LIBRARY" and root is None:
                root = (await roots(session, user.id))[NodeRole.LIBRARY_ROOT].id
            for query in dict.fromkeys(data.queries):
                page = await search_service(
                    session,
                    user.id,
                    config,
                    q=query,
                    node_id=root,
                    type=NodeType(data.type) if data.type else None,
                    limit=data.limit,
                    budget=budget,
                )
                if not page["nodes"]:
                    unmatched.append(query)
                for node in page["nodes"]:
                    merged.setdefault(node["id"], node | {"matched_queries": []})[
                        "matched_queries"
                    ].append(query)
            cards = await node_cards(session, user.id, config, list(merged.values()))
        for card, node in zip(cards, merged.values(), strict=True):
            card["matched_queries"] = node["matched_queries"]
        return {"nodes": cards, "unmatched_queries": unmatched}

    @task_tool(LibraryRead)
    async def read_library(**values):
        """Read a deck/folder/reference in one call, with metadata and exact summary.
        CONTENT returns distinct senses including definitions, examples and learning state;
        STRUCTURE lists immediate child nodes. Omit node_id for the whole Library. Content
        supports lexical query, learning state and SQL ordering (MASTERY_ASC = lowest Elo
        first). Continue with unchanged cursor and the same filters. Never treat children
        as deck membership; an empty STRUCTURE page says nothing about a deck's senses.
        """
        data = LibraryRead(**values)
        async with resources.sessions() as session:
            root = data.node_id or (await roots(session, user.id))[NodeRole.LIBRARY_ROOT].id
            detail = await nodes.node_details(session, root, user.id, config)
            node = node_projection(detail, user.id) | {
                "path": [{"node_id": r["id"], "name": r["name"]} for r in detail["breadcrumbs"]],
                "reference_available": detail["reference_available"],
            }
            count = (await summaries(session, user.id, config, [root]))[0]
            if data.view == "STRUCTURE":
                page = await nodes.list_nodes(
                    session, user.id, root, data.cursor, config, limit=data.limit
                )
                page["nodes"] = await node_cards(session, user.id, config, page["nodes"])
            else:
                target = await readable(session, root, user.id, config)
                page = await sense_page(
                    session,
                    target,
                    user.id,
                    config,
                    resources.lexicon,
                    data.cursor,
                    state=data.state,
                    q=data.query,
                    sort=data.sort,
                    limit=data.limit,
                    include="examples",
                )
                page["senses"] = [
                    {
                        k: s[k]
                        for k in ("sense_id", "word_id", "lemma", "pos", "definition", "learning")
                    }
                    | {"examples": [e.content for e in s["examples"][:1]]}
                    for s in page["senses"]
                ]
            return {"node": node, "summary": count} | page

    @task_tool(LearningOverview)
    async def learning_overview(**values):
        """Read exact summaries for Library scopes together. Optional activity is account-
        wide, not per deck; schedules are scoped and future-only. Supply activity_window and
        schedule_window separately if dates differ. Read CONTENT for actual sense-level
        mastery, not invented accuracy. Dates use the user's timezone.
        """
        data = LearningOverview(**values)
        ids = data.node_ids or [None]
        async with resources.sessions() as session:
            budget = ScopeBudget(user.id)
            result = {"summaries": await summaries(session, user.id, config, ids, budget=budget)}
            if "activity" in data.include:
                dates = data.activity_window
                result["activity"] = await activity(
                    session,
                    user.id,
                    config,
                    dates.start_date if dates else None,
                    dates.end_date if dates else None,
                )
            if "schedule" in data.include:
                dates = data.schedule_window
                result["schedules"] = await schedules(
                    session,
                    user.id,
                    config,
                    ids,
                    dates.start_date if dates else None,
                    dates.end_date if dates else None,
                    budget=budget,
                )
            return result

    async def generation_items(results):
        completed = [r["word_id"] for r in results if r["status"] == "SUCCEEDED"]
        senses = (
            (await vocabulary(resources, user, config, completed))["senses"] if completed else []
        )
        groups = {}
        for sense in senses:
            groups.setdefault(sense["word_id"], []).append(sense)
        if set(completed) - groups.keys():
            raise Problem(409, "learning_content_changed")
        return [
            {k: r[k] for k in ("task_id", "status", "word_id", "error")}
            | (
                {"lemma": groups[r["word_id"]][0]["lemma"], "senses": groups[r["word_id"]]}
                if r["status"] == "SUCCEEDED"
                else {}
            )
            for r in results
        ]

    @task_tool(WordGeneration)
    async def generate_words(**values):
        """Generate or reuse up to 10 words/expressions. Supply words as strings, not definitions
        or a language name. Lexi selects sources and normalizes lemmas. Returns completed senses
        or RUNNING task IDs; read unfinished tasks with get_generations before adding senses.
        """
        data = WordGeneration(**values)
        results = []
        for word in dict.fromkeys(data.words):
            try:
                result = await resources.generations.submit(word)
                results.append(result | {"target": word})
            except Problem as exc:
                logger.warning("assistant_word_generation_failed", word=word, error=exc.code)
                results.append(
                    {
                        "target": word,
                        "task_id": None,
                        "status": "FAILED",
                        "word_id": None,
                        "error": exc.code,
                    }
                )
        await resources.generations.wait(
            [r["task_id"] for r in results if r["task_id"] is not None]
        )
        for result in results:
            if result["task_id"] is not None:
                result.update(resources.generations.status(result["task_id"]))
        items = await generation_items(results)
        return {
            "items": [
                item | {"target": r["target"]} for item, r in zip(items, results, strict=True)
            ]
        }

    @task_tool(GenerationRead)
    async def get_generations(**values):
        """Read multiple Word-generation tasks and include completed lexical senses.
        RUNNING means unfinished; do not claim success or repeatedly poll in a tight loop.
        """
        data = GenerationRead(**values)
        await resources.generations.wait(data.task_ids)
        results = []
        for identifier in data.task_ids:
            try:
                results.append(resources.generations.status(identifier))
            except Problem as exc:
                results.append(
                    {"task_id": identifier, "status": "FAILED", "word_id": None, "error": exc.code}
                )
        return {"items": await generation_items(results)}

    @task_tool(NodeCreate)
    async def create_node(**values):
        """Create a folder, deck or reference. Decks take existing sense_ids directly;
        omitted parent_id means Personal. Publishing requires confirm_publication. Returns
        saved metadata/counts, not the whole membership list.
        """
        async with resources.sessions() as session:
            result = await nodes.create_node(session, user.id, NodeCreate(**values), config)
        return await saved_node(resources, user.id, config, result)

    @task_tool(NodeUpdate)
    async def update_node(**values):
        """Atomically update supplied name/description and/or add/remove deck sense IDs.
        Null or omitted name/description means unchanged. Use clear_description=true to clear
        description. Membership changes apply
        only to decks and preserve unrelated senses. Returns actual added/removed counts.
        """
        data = NodeUpdate(**values)
        metadata = data.model_dump(include={"name", "description"}, exclude_none=True)
        if data.clear_description:
            metadata["description"] = None
        delta = SenseDelta(add=data.add_sense_ids, remove=data.remove_sense_ids)
        async with resources.sessions() as session:
            result = await nodes.update_node(
                session,
                user.id,
                data.node_id,
                NodePatch(**metadata) if metadata else None,
                delta if delta.add or delta.remove else None,
                config,
            )
        return await saved_node(resources, user.id, config, result)

    async def batch_nodes(data, operation):
        items, saved = [], []
        for identifier in data.node_ids:
            try:
                async with resources.sessions() as session:
                    result = await operation(session, identifier)
                items.append({"source_node_id": identifier, "status": "SUCCEEDED"})
                if result:
                    saved.append((items[-1], result))
            except Problem as exc:
                logger.warning(
                    "assistant_batch_node_failed",
                    node_id=str(identifier),
                    error=exc.code,
                )
                items.append({"source_node_id": identifier, "status": "FAILED", "error": exc.code})
        if saved:
            enriched = await saved_nodes(resources, user.id, config, [r for _, r in saved])
            for (item, _), card in zip(saved, enriched, strict=True):
                item.update(card)
        return {"items": items}

    @task_tool(NodeMove)
    async def move_nodes(**values):
        """Move owned nodes to one folder. Each item is atomic; reports partial failures.
        Entering Published requires confirm_publication; retain_personal_reference optionally
        keeps an alias at the old location. Does not change membership or metadata.
        """
        data = NodeMove(**values)
        move = Move(**data.model_dump(exclude={"node_ids"}))
        return await batch_nodes(
            data,
            lambda session, identifier: nodes.move_node(session, user.id, identifier, move, config),
        )

    @task_tool(NodeCopy)
    async def copy_nodes(**values):
        """Copy owned nodes/subtrees to one folder. Each item is atomic; returns source-to-
        new-node IDs and per-item failures. Publishing needs confirm_publication.
        """
        data = NodeCopy(**values)
        destination = NodeDestination(**data.model_dump(exclude={"node_ids"}))
        return await batch_nodes(
            data,
            lambda session, identifier: nodes.copy_node(
                session, user.id, identifier, destination, config
            ),
        )

    @task_tool(NodeBatch)
    async def delete_nodes(**values):
        """Delete owned normal nodes and descendants. Each item is atomic; return exact
        success/failure per node. System roots are protected; learning state is preserved.
        """
        return await batch_nodes(
            NodeBatch(**values),
            lambda session, identifier: nodes.delete_node(session, user.id, identifier, config),
        )

    def preference_projection(result):
        return {
            k: result[k]
            for k in ("settings", "effective_learning", "learning_restriction", "learning_options")
        }

    @task_tool()
    async def get_preferences():
        """Read saved settings, effective learning selection and current plan restrictions.
        Saved typed preferences may differ from formats actually available to this user.
        """
        async with resources.sessions() as session:
            return preference_projection(await profile(user, config, session))

    @task_tool(PreferencesPatch.model_json_schema())
    async def update_preferences(**values):
        """Update only requested settings; preserve other preferences. Return saved and
        effective learning configuration/plan restrictions. Does not change the user's plan.
        """
        async with resources.sessions() as session:
            return preference_projection(
                await patch_settings(PreferencesPatch(**values), user, config, session)
            )

    return [
        search_words,
        read_vocabulary,
        search_nodes,
        read_library,
        learning_overview,
        generate_words,
        get_generations,
        create_node,
        update_node,
        move_nodes,
        copy_nodes,
        delete_nodes,
        get_preferences,
        update_preferences,
    ]
