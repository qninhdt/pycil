"""Task-oriented tools over the same authorized product services as HTTP."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import wraps
from typing import Any, Protocol
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from langchain_core.tools import BaseTool, ToolException, tool
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.account.profiles import profile
from pycil.account.schemas import PreferencesPatch
from pycil.account.settings import update_preferences as save_preferences
from pycil.app.config import AppConfig
from pycil.app.http import Problem
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
from pycil.infrastructure.observability import get_logger
from pycil.library import nodes
from pycil.library.access import readable
from pycil.library.models import NodeRole, NodeSpace, NodeType
from pycil.library.schemas import LibraryView, NodeCreate, NodeDestination, NodePatch, SenseDelta
from pycil.library.schemas import NodeMove as Move
from pycil.library.scope import ScopeBudget
from pycil.library.search import search_nodes as search_service
from pycil.library.senses import sense_page
from pycil.library.tree import roots
from pycil.study.progress import activity, schedules, summaries
from pycil.vocabulary.enums import JobState
from pycil.vocabulary.errors import InvalidResourceError

logger = get_logger(__name__)
# Search previews carry one sample; expanded context uses the projection policy.
SEARCH_PREVIEW_EXAMPLES = 1


MUTATION_TOOLS = {
    "create_node",
    "update_node",
    "move_nodes",
    "copy_nodes",
    "delete_nodes",
    "generate_words",
    "update_preferences",
}


class AssistantResources(Protocol):
    sessions: async_sessionmaker[AsyncSession]
    search: Any
    sense_cache: Any
    generations: Any


def validation_message(error: Any) -> str:
    details = (
        error.errors(include_input=False, include_context=False, include_url=False)
        if hasattr(error, "errors")
        else str(error)
    )
    return json.dumps(
        {
            "error": "invalid_tool_arguments",
            "details": details,
        },
        separators=(",", ":"),
    )


def task_tool(
    schema: type[BaseModel] | dict[str, Any] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], BaseTool]:
    """Keep native tool results JSON-safe and validation feedback actionable."""

    def decorate(function: Callable[..., Awaitable[Any]]) -> BaseTool:
        @wraps(function)
        async def invoke(**values: Any) -> Any:
            try:
                return jsonable_encoder(await function(**values))
            except ValidationError as error:
                raise ToolException(validation_message(error)) from None

        result = tool(args_schema=schema)(invoke)
        result.handle_tool_error = True
        result.handle_validation_error = validation_message
        return result

    return decorate


def tools(
    resources: AssistantResources,
    user: UUID,
    config: AppConfig,
) -> list[BaseTool]:
    @task_tool(WordSearch)
    async def search_words(**values: Any) -> Any:
        """Search existing Words for up to 10 terms. Limit is per query; hits include all
        sense IDs/definitions. Use generate_words for missing words. Optional include adds examples,
        lexical_details, personal learning or containing decks. Search is lexical, not semantic.
        """
        data = WordSearch(**values)
        queries = list(dict.fromkeys(data.queries))

        async def search(query: str) -> list[Any]:
            try:
                return (await resources.search.search(query)).items
            except InvalidResourceError:
                raise Problem(422, "invalid_lexical_query") from None

        pages: list[list[Any]] = list(await asyncio.gather(*(search(q) for q in queries)))
        merged: dict[int, dict[str, Any]] = {}
        unmatched: list[str] = []
        for query, hits in zip(queries, pages, strict=True):
            if not hits:
                unmatched.append(query)
            for hit in hits[: data.limit]:
                item: dict[str, Any] = hit.model_dump(mode="json")
                identity: int = item["word_id"]
                merged.setdefault(identity, item | {"matched_queries": []})[
                    "matched_queries"
                ].append(query)
        word_ids: list[int] = [item["word_id"] for item in merged.values()]
        senses = (
            (await vocabulary(resources, user, config, word_ids=word_ids, include=data.include))[
                "senses"
            ]
            if word_ids
            else []
        )
        groups: dict[int, list[dict[str, Any]]] = {}
        for sense in senses:
            groups.setdefault(sense["word_id"], []).append(sense)
        for item in merged.values():
            item["senses"] = groups.get(item["word_id"], [])
        return {"items": list(merged.values()), "unmatched_queries": unmatched}

    @task_tool(VocabularyRead)
    async def read_vocabulary(**values: Any) -> Any:
        """Read known Word/sense IDs in one batch. Returns deduplicated sense definitions;
        include examples, lexical_details, learning or sources only when needed. Word IDs and
        sense IDs are different identifiers.
        """
        data = VocabularyRead(**values)
        return await vocabulary(
            resources, user, config, data.word_ids, data.sense_ids, data.include
        )

    @task_tool(NodeSearch)
    async def search_nodes(**values: Any) -> Any:
        """Find folders/decks by multiple names. library defaults to the user's whole
        Library, or restricts to node_id; published searches public Discovery. Limit is per
        query. Returns one merged list with safe paths, editability and exact summaries.
        """
        data = NodeSearch(**values)
        merged: dict[UUID, dict[str, Any]] = {}
        unmatched: list[str] = []
        budget = ScopeBudget(user)
        async with resources.sessions() as session:
            root = data.node_id
            if data.scope == NodeSpace.LIBRARY and root is None:
                root = (await roots(session, user))[NodeRole.LIBRARY_ROOT].id
            for query in dict.fromkeys(data.queries):
                page = await search_service(
                    session,
                    user,
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
            cards = await node_cards(session, user, config, list(merged.values()))
        for card, node in zip(cards, merged.values(), strict=True):
            card["matched_queries"] = node["matched_queries"]
        return {"nodes": cards, "unmatched_queries": unmatched}

    @task_tool(LibraryRead)
    async def read_library(**values: Any) -> Any:
        """Read a deck/folder/reference in one call, with metadata and exact summary.
        content returns distinct senses including definitions, examples and learning state;
        structure lists immediate child nodes. Omit node_id for the whole Library. Content
        supports lexical query, learning state and SQL ordering (mastery_asc = lowest Elo
        first). Continue with unchanged cursor and the same filters. Never treat children
        as deck membership; an empty structure page says nothing about a deck's senses.
        """
        data = LibraryRead(**values)
        async with resources.sessions() as session:
            root = data.node_id or (await roots(session, user))[NodeRole.LIBRARY_ROOT].id
            detail = await nodes.node_details(session, root, user, config)
            node = node_projection(detail, user) | {
                "path": [{"node_id": r["id"], "name": r["name"]} for r in detail["breadcrumbs"]],
                "reference_available": detail["reference_available"],
            }
            count = (await summaries(session, user, config, [root]))[0]
            if data.view == LibraryView.STRUCTURE:
                page = await nodes.list_nodes(
                    session, user, root, data.cursor, config, limit=data.limit
                )
                page["nodes"] = await node_cards(session, user, config, page["nodes"])
            else:
                target = await readable(session, root, user, config)
                page = await sense_page(
                    session,
                    target,
                    user,
                    config,
                    resources.sessions,
                    data.cursor,
                    state=data.state,
                    q=data.query,
                    sort=data.sort,
                    limit=data.limit,
                    include="examples",
                    sense_cache=resources.sense_cache,
                )
                page["senses"] = [
                    {
                        k: s[k]
                        for k in ("sense_id", "word_id", "lemma", "pos", "definition", "learning")
                    }
                    | {"examples": [e.content for e in s["examples"][:SEARCH_PREVIEW_EXAMPLES]]}
                    for s in page["senses"]
                ]
            return {"node": node, "summary": count} | page

    @task_tool(LearningOverview)
    async def learning_overview(**values: Any) -> Any:
        """Read exact summaries for Library scopes together. Optional activity is account-
        wide, not per deck; schedules are scoped and future-only. Supply activity_window and
        schedule_window separately if dates differ. Read content for actual sense-level
        mastery, not invented accuracy. Dates use the user's timezone.
        """
        data = LearningOverview(**values)
        ids = data.node_ids or [None]
        async with resources.sessions() as session:
            budget = ScopeBudget(user)
            result: dict[str, Any] = {
                "summaries": await summaries(session, user, config, ids, budget=budget)
            }
            if "activity" in data.include:
                dates = data.activity_window
                result["activity"] = await activity(
                    session,
                    user,
                    config,
                    dates.start_date if dates else None,
                    dates.end_date if dates else None,
                )
            if "schedule" in data.include:
                dates = data.schedule_window
                result["schedules"] = await schedules(
                    session,
                    user,
                    config,
                    ids,
                    dates.start_date if dates else None,
                    dates.end_date if dates else None,
                    budget=budget,
                )
            return result

    async def generation_items(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        completed: list[int] = [
            int(r["word_id"]) for r in results if r["status"] == JobState.SUCCEEDED
        ]
        senses = (
            (await vocabulary(resources, user, config, completed))["senses"] if completed else []
        )
        groups: dict[int, list[dict[str, Any]]] = {}
        for sense in senses:
            groups.setdefault(sense["word_id"], []).append(sense)
        if set(completed) - groups.keys():
            raise Problem(409, "learning_content_changed")
        return [
            {k: r[k] for k in ("task_id", "status", "word_id", "error")}
            | (
                {"lemma": groups[r["word_id"]][0]["lemma"], "senses": groups[r["word_id"]]}
                if r["status"] == JobState.SUCCEEDED
                else {}
            )
            for r in results
        ]

    @task_tool(WordGeneration)
    async def generate_words(**values: Any) -> Any:
        """Generate or reuse up to 10 words/expressions. Supply words as strings, not definitions
        or a language name. Vocabulary generation selects sources and normalizes lemmas.
        Returns completed senses or running task IDs; read unfinished tasks with get_generations
        before adding senses.
        """
        data = WordGeneration(**values)
        results: list[dict[str, Any]] = []
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
                        "status": JobState.FAILED,
                        "word_id": None,
                        "error": exc.code,
                    }
                )
        await resources.generations.wait(
            [r["task_id"] for r in results if r["task_id"] is not None]
        )
        for result in results:
            if result["task_id"] is not None:
                result.update(await resources.generations.status(result["task_id"]))
        items = await generation_items(results)
        return {
            "items": [
                item | {"target": r["target"]} for item, r in zip(items, results, strict=True)
            ]
        }

    @task_tool(GenerationRead)
    async def get_generations(**values: Any) -> Any:
        """Read multiple Word-generation tasks and include completed lexical senses.
        RUNNING means unfinished; do not claim success or repeatedly poll in a tight loop.
        """
        data = GenerationRead(**values)
        await resources.generations.wait(data.task_ids)
        results: list[dict[str, Any]] = []
        for identifier in data.task_ids:
            try:
                results.append(await resources.generations.status(identifier))
            except Problem as exc:
                results.append(
                    {
                        "task_id": identifier,
                        "status": JobState.FAILED,
                        "word_id": None,
                        "error": exc.code,
                    }
                )
        return {"items": await generation_items(results)}

    @task_tool(NodeCreate)
    async def create_node(**values: Any) -> Any:
        """Create a folder, deck or reference. Decks take existing sense_ids directly;
        omitted parent_id means Personal. Publishing requires confirm_publication. Returns
        saved metadata/counts, not the whole membership list.
        """
        async with resources.sessions() as session:
            result = await nodes.create_node(session, user, NodeCreate(**values), config)
        return await saved_node(resources, user, config, result)

    @task_tool(NodeUpdate)
    async def update_node(**values: Any) -> Any:
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
                user,
                data.node_id,
                NodePatch(**metadata) if metadata else None,
                delta if delta.add or delta.remove else None,
                config,
            )
        return await saved_node(resources, user, config, result)

    async def batch_nodes(
        data: NodeMove | NodeCopy | NodeBatch,
        operation: Callable[[AsyncSession, UUID], Awaitable[Any]],
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        saved: list[tuple[dict[str, Any], Any]] = []
        for identifier in data.node_ids:
            try:
                async with resources.sessions() as session:
                    result = await operation(session, identifier)
                items.append({"source_node_id": identifier, "status": JobState.SUCCEEDED})
                if result:
                    saved.append((items[-1], result))
            except Problem as exc:
                logger.warning(
                    "assistant_batch_node_failed",
                    node_id=str(identifier),
                    error=exc.code,
                )
                items.append(
                    {"source_node_id": identifier, "status": JobState.FAILED, "error": exc.code}
                )
        if saved:
            enriched = await saved_nodes(resources, user, config, [r for _, r in saved])
            for (item, _), card in zip(saved, enriched, strict=True):
                item.update(card)
        return {"items": items}

    @task_tool(NodeMove)
    async def move_nodes(**values: Any) -> Any:
        """Move owned nodes to one folder. Each item is atomic; reports partial failures.
        Entering Published requires confirm_publication; retain_personal_reference optionally
        keeps an alias at the old location. Does not change membership or metadata.
        """
        data = NodeMove(**values)
        move = Move(**data.model_dump(exclude={"node_ids"}))
        return await batch_nodes(
            data,
            lambda session, identifier: nodes.move_node(session, user, identifier, move, config),
        )

    @task_tool(NodeCopy)
    async def copy_nodes(**values: Any) -> Any:
        """Copy owned nodes/subtrees to one folder. Each item is atomic; returns source-to-
        new-node IDs and per-item failures. Publishing needs confirm_publication.
        """
        data = NodeCopy(**values)
        destination = NodeDestination(**data.model_dump(exclude={"node_ids"}))
        return await batch_nodes(
            data,
            lambda session, identifier: nodes.copy_node(
                session, user, identifier, destination, config
            ),
        )

    @task_tool(NodeBatch)
    async def delete_nodes(**values: Any) -> Any:
        """Delete owned normal nodes and descendants. Each item is atomic; return exact
        success/failure per node. System roots are protected; learning state is preserved.
        """
        return await batch_nodes(
            NodeBatch(**values),
            lambda session, identifier: nodes.delete_node(session, user, identifier, config),
        )

    def preference_projection(result: Mapping[str, Any]) -> dict[str, Any]:
        return {
            k: result[k]
            for k in ("settings", "effective_learning", "learning_restriction", "learning_options")
        }

    @task_tool()
    async def get_preferences(**values: Any) -> Any:
        """Read saved settings, effective learning selection and current plan restrictions.
        Saved typed preferences may differ from formats actually available to this user.
        """
        async with resources.sessions() as session:
            return preference_projection(await profile(user, config, session))

    @task_tool(PreferencesPatch.model_json_schema())
    async def update_preferences(**values: Any) -> Any:
        """Update only requested settings; preserve other preferences. Return saved and
        effective learning configuration/plan restrictions. Does not change the user's plan.
        """
        async with resources.sessions() as session:
            updated = await save_preferences(session, user, PreferencesPatch(**values), config)
            return preference_projection(await profile(updated.id, config, session))

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
