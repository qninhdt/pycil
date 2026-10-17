"""Task-oriented tools over the same authorized product services as HTTP."""

import asyncio
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import wraps
from itertools import batched
from typing import Protocol, cast
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from langchain_core.tools import BaseTool, ToolException, tool
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from taskiq import AsyncBroker, AsyncTaskiqTask
from taskiq.exceptions import TaskiqResultTimeoutError

from pycil.account.config import AccountConfig
from pycil.account.profiles import profile
from pycil.account.schemas import PreferencesPatch
from pycil.account.settings import update_preferences as save_preferences
from pycil.assistant.config import AssistantConfig
from pycil.assistant.schemas import (
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
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.jobs.config import JobsConfig
from pycil.library import nodes
from pycil.library.access import readable, reference_visible, visible
from pycil.library.config import LibraryConfig
from pycil.library.models import Node, NodePath, NodeRole, NodeSpace, NodeType
from pycil.library.nodes import list_nodes
from pycil.library.schemas import LibraryView, NodeCreate, NodeDestination, NodePatch, SenseDelta
from pycil.library.schemas import NodeMove as Move
from pycil.library.scope import ScopeBudget
from pycil.library.search import search_nodes as search_service
from pycil.library.senses import sense_page
from pycil.library.tree import roots
from pycil.observability import get_logger
from pycil.study.config import StudyConfig
from pycil.study.progress import activity, schedules, summaries
from pycil.study.types import SummaryDict
from pycil.utils.errors import Conflict, InvalidInput, NotFound, OperationError
from pycil.vocabulary.config import VocabularyConfig
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.generation.tasks import request_generation
from pycil.vocabulary.models import Sense as SenseRow
from pycil.vocabulary.models import Word
from pycil.vocabulary.schemas import Example, Sense, sense_adapter
from pycil.vocabulary.search import ReferenceHit, SearchIndex, WordHit
from pycil.vocabulary.words import get_sense_previews, get_senses, viewer_context

logger = get_logger(__name__)
# Search previews carry one sample; expanded context uses the projection policy.
SEARCH_PREVIEW_EXAMPLES = 1


MUTATION_TOOLS = {
    "create_node",
    "update_node",
    "move_nodes",
    "copy_nodes",
    "delete_nodes",
    "update_preferences",
    "generate_words",
}


class AssistantResources(Protocol):
    redis: Redis
    broker: AsyncBroker
    sessions: async_sessionmaker[AsyncSession]
    search: SearchIndex
    sense_store: InMemoryStore[int, Sense]


class AssistantToolConfig(Protocol):
    vocabulary: VocabularyConfig
    library: LibraryConfig
    study: StudyConfig
    account: AccountConfig
    assistant: AssistantConfig
    jobs: JobsConfig


async def vocabulary(
    resources: AssistantResources,
    user: UUID,
    config: AssistantToolConfig,
    word_ids: Sequence[int] = (),
    sense_ids: Sequence[int] = (),
    include: Sequence[str] = (),
) -> dict[str, list[dict[str, object]]]:
    word_ids_set = set(word_ids)
    sense_ids_set = set(sense_ids)
    async with resources.sessions() as session:
        if word_ids_set:
            found = set(
                (await session.scalars(select(Word.id).where(Word.id.in_(word_ids_set)))).all()
            )
            if found != word_ids_set:
                raise NotFound("word_not_found")
        rows = list(
            (
                await session.execute(
                    select(SenseRow.id, SenseRow.word_id)
                    .where(or_(SenseRow.word_id.in_(word_ids_set), SenseRow.id.in_(sense_ids_set)))
                    .order_by(SenseRow.id)
                    .limit(config.vocabulary.preview.max_word_senses + 1)
                )
            ).all()
        )
        if len(rows) > config.vocabulary.preview.max_word_senses:
            raise InvalidInput("lexical_batch_too_large")
        identifiers: list[int] = [int(r[0]) for r in rows]
        if not sense_ids_set <= set(identifiers):
            raise NotFound("sense_not_found")
        context_data = await viewer_context(
            session,
            user,
            identifiers,
            library_config=config.library,
            study_config=config.study,
            policy=config.vocabulary.preview,
            include_sources="sources" in include,
            max_senses=config.vocabulary.preview.max_word_senses,
        )
        senses_list = cast(list[dict[str, object]], context_data["senses"])
        context = (
            {cast(int, s["sense_id"]): s for s in senses_list}
            if identifiers and set(include) & {"learning", "sources"}
            else {}
        )
    facts: dict[int, dict[str, object]] = {
        int(s["sense_id"]): dict(s)
        for s in await get_sense_previews(resources.sessions, identifiers)
    }
    native = (
        {
            s.id: s
            for s in await get_senses(resources.sessions, identifiers, store=resources.sense_store)
        }
        if set(include) & {"examples", "lexical_details"}
        else {}
    )
    result: list[dict[str, object]] = []
    for identifier in identifiers:
        if identifier not in facts or (
            set(include) & {"examples", "lexical_details"} and identifier not in native
        ):
            raise Conflict("learning_content_changed")
        item: dict[str, object] = {
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
                for e in native[identifier].examples[: config.vocabulary.preview.inline_examples]
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


def node_projection(node: Mapping[str, object], user_id: UUID) -> dict[str, object]:
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
    config: AssistantToolConfig,
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if not rows:
        return []
    identifiers: list[UUID] = [cast(UUID, r["id"]) for r in rows]
    ancestor = Node.__table__.alias("ancestor")
    paths: dict[UUID, list[dict[str, object]]] = {i: [] for i in identifiers}
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
    counts: list[SummaryDict] = []
    size = config.study.limits.max_summary_nodes
    budget = ScopeBudget(user_id)
    for batch in batched(identifiers, size, strict=False):
        counts.extend(
            await summaries(
                session,
                user_id,
                config.study,
                batch,
                budget=budget,
                library_config=config.library,
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


async def saved_nodes(
    resources: AssistantResources,
    user_id: UUID,
    config: AssistantToolConfig,
    results: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for result in results:
        item = node_projection(result, user_id)
        if "sense_ids" in result:
            item["sense_count"] = len(cast(Sequence[object], result["sense_ids"]))
        for key in ("added_count", "removed_count", "retained_reference_id"):
            if key in result:
                item[key] = result[key]
        items.append(item)
    # The write already committed; enrichment failure must not report it as failed.
    async with resources.sessions() as session:
        try:
            counts = await summaries(
                session,
                user_id,
                config.study,
                [cast(UUID, r["id"]) for r in results],
                library_config=config.library,
            )
        except OperationError as exc:
            for item in items:
                item["summary_error"] = exc.code
        else:
            for item, count in zip(items, counts, strict=True):
                item["summary"] = count
    return items


async def saved_node(
    resources: AssistantResources,
    user_id: UUID,
    config: AssistantToolConfig,
    result: Mapping[str, object],
) -> dict[str, object]:
    return (await saved_nodes(resources, user_id, config, [result]))[0]


def validation_message(error: ValidationError | Exception | object) -> str:
    details = (
        error.errors(include_input=False, include_context=False, include_url=False)
        if isinstance(error, ValidationError)
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
    schema: type[BaseModel] | None = None,
) -> Callable[[Callable[..., Awaitable[object]]], BaseTool]:
    """Keep native tool results JSON-safe and validation feedback actionable."""

    def decorate(function: Callable[..., Awaitable[object]]) -> BaseTool:
        @wraps(function)
        async def invoke(**values: object) -> object:
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
    config: AssistantToolConfig,
) -> list[BaseTool]:
    @task_tool(WordSearch)
    async def search_words(**values: object) -> object:
        """Search Words and dictionary references for up to 10 terms. Limit is per query;
        Words include sense IDs/definitions; references include reference_id for generate_words.
        Optional include adds examples,
        lexical_details, personal learning or containing decks. Search is lexical, not semantic.
        """
        data = WordSearch.model_validate(values)
        queries = list(dict.fromkeys(data.queries))

        async def search(query: str) -> Sequence[WordHit | ReferenceHit]:
            try:
                return (await resources.search.search(query, include_reference=True)).items
            except InvalidResourceError:
                raise InvalidInput("invalid_lexical_query") from None

        pages: list[Sequence[WordHit | ReferenceHit]] = list(
            await asyncio.gather(*(search(q) for q in queries))
        )
        merged: dict[tuple[str, int | str], dict[str, object]] = {}
        matched_queries: dict[tuple[str, int | str], list[str]] = defaultdict(list)
        unmatched: list[str] = []
        for query, hits in zip(queries, pages, strict=True):
            if not hits:
                unmatched.append(query)
            for hit in hits[: data.limit]:
                item: dict[str, object] = hit.model_dump(mode="json")
                identity = (
                    ("word", hit.word_id)
                    if isinstance(hit, WordHit)
                    else ("reference", hit.reference_id)
                )
                if identity not in merged:
                    merged[identity] = item
                matched_queries[identity].append(query)
        for identity, item in merged.items():
            item["matched_queries"] = matched_queries[identity]
        word_ids = [w for item in merged.values() if isinstance(w := item.get("word_id"), int)]
        senses = (
            (await vocabulary(resources, user, config, word_ids=word_ids, include=data.include))[
                "senses"
            ]
            if word_ids
            else []
        )
        groups: dict[int, list[dict[str, object]]] = {}
        for sense in senses:
            w_id = sense.get("word_id")
            if isinstance(w_id, int):
                groups.setdefault(w_id, []).append(sense)
        for item in merged.values():
            w_id = item.get("word_id")
            if isinstance(w_id, int):
                item["senses"] = groups.get(w_id, [])
        return {"items": list(merged.values()), "unmatched_queries": unmatched}

    @task_tool(VocabularyRead)
    async def read_vocabulary(**values: object) -> object:
        """Read known Word/sense IDs in one batch. Returns deduplicated sense definitions;
        include examples, lexical_details, learning or sources only when needed. Word IDs and
        sense IDs are different identifiers.
        """
        data = VocabularyRead.model_validate(values)
        return await vocabulary(
            resources, user, config, data.word_ids, data.sense_ids, data.include
        )

    @task_tool(NodeSearch)
    async def search_nodes(**values: object) -> object:
        """Find folders/decks by multiple names. library defaults to the user's whole
        Library, or restricts to node_id; published searches public Discovery. Limit is per
        query. Returns one merged list with safe paths, editability and exact summaries.
        """
        data = NodeSearch.model_validate(values)
        merged: dict[UUID, dict[str, object]] = {}
        matched_queries: dict[UUID, list[str]] = defaultdict(list)
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
                    config.library,
                    q=query,
                    node_id=root,
                    type=NodeType(data.type) if data.type else None,
                    limit=data.limit,
                    budget=budget,
                )
                if not page["nodes"]:
                    unmatched.append(query)
                for node in page["nodes"]:
                    node_id = UUID(str(node["id"]))
                    if node_id not in merged:
                        merged[node_id] = dict(node)
                    matched_queries[node_id].append(query)
            cards = await node_cards(session, user, config, list(merged.values()))
        for card, node in zip(cards, merged.values(), strict=True):
            card["matched_queries"] = matched_queries[UUID(str(node["id"]))]
        return {"nodes": cards, "unmatched_queries": unmatched}

    @task_tool(LibraryRead)
    async def read_library(**values: object) -> object:
        """Read a deck/folder/reference in one call, with metadata and exact summary.
        content returns distinct senses including definitions, examples and learning state;
        structure lists immediate child nodes. Omit node_id for the whole Library. Content
        supports lexical query, learning state and SQL ordering (mastery_asc = lowest Elo
        first). Continue with unchanged cursor and the same filters. Never treat children
        as deck membership; an empty structure page says nothing about a deck's senses.
        """
        data = LibraryRead.model_validate(values)
        async with resources.sessions() as session:
            root = data.node_id or (await roots(session, user))[NodeRole.LIBRARY_ROOT].id
            detail = await nodes.node_details(session, root, user)
            breadcrumbs = cast(list[dict[str, object]], detail["breadcrumbs"])
            node = node_projection(detail, user) | {
                "path": [{"node_id": r["id"], "name": r["name"]} for r in breadcrumbs],
                "reference_available": detail["reference_available"],
            }
            count = (
                await summaries(
                    session,
                    user,
                    config.study,
                    [root],
                    library_config=config.library,
                )
            )[0]
            if data.view == LibraryView.STRUCTURE:
                structure_page = await list_nodes(
                    session, user, root, data.cursor, config.library, limit=data.limit
                )
                nodes_page: dict[str, object] = dict(structure_page)
                nodes_page["nodes"] = await node_cards(
                    session, user, config, structure_page["nodes"]
                )
                page = nodes_page
            else:
                target = await readable(session, root, user)
                senses_page = await sense_page(
                    session,
                    target,
                    user,
                    config.library,
                    resources.sessions,
                    data.cursor,
                    state=data.state,
                    q=data.query,
                    sort=data.sort,
                    limit=data.limit,
                    include="examples",
                    sense_store=resources.sense_store,
                    study_config=config.study,
                )
                senses_list = cast(list[dict[str, object]], senses_page["senses"])
                senses_page["senses"] = [
                    {
                        k: s[k]
                        for k in ("sense_id", "word_id", "lemma", "pos", "definition", "learning")
                    }
                    | {
                        "examples": [
                            e.content
                            for e in cast(list[Example], s["examples"])[:SEARCH_PREVIEW_EXAMPLES]
                        ]
                    }
                    for s in senses_list
                ]
                page = senses_page
            return {"node": node, "summary": count} | page

    @task_tool(LearningOverview)
    async def learning_overview(**values: object) -> object:
        """Read exact summaries for Library scopes together. Optional activity is account-
        wide, not per deck; schedules are scoped and future-only. Supply activity_window and
        schedule_window separately if dates differ. Read content for actual sense-level
        mastery, not invented accuracy. Dates use the user's timezone.
        """
        data = LearningOverview.model_validate(values)
        ids = data.node_ids or [None]
        async with resources.sessions() as session:
            budget = ScopeBudget(user)
            result: dict[str, object] = {
                "summaries": await summaries(
                    session,
                    user,
                    config.study,
                    ids,
                    budget=budget,
                    library_config=config.library,
                )
            }
            if "activity" in data.include:
                dates = data.activity_window
                result["activity"] = await activity(
                    session,
                    user,
                    config.study,
                    dates.start_date if dates else None,
                    dates.end_date if dates else None,
                    account_config=config.account,
                )
            if "schedule" in data.include:
                dates = data.schedule_window
                result["schedules"] = await schedules(
                    session,
                    user,
                    config.study,
                    ids,
                    dates.start_date if dates else None,
                    dates.end_date if dates else None,
                    budget=budget,
                    account_config=config.account,
                    library_config=config.library,
                )
            return result

    @task_tool(NodeCreate)
    async def create_node(**values: object) -> object:
        """Create a folder, deck or reference. Decks take existing sense_ids directly;
        omitted parent_id means Personal. Publishing requires confirm_publication. Returns
        saved metadata/counts, not the whole membership list.
        """
        async with resources.sessions() as session:
            result = await nodes.create_node(
                session, user, NodeCreate.model_validate(values), config.library
            )
        return await saved_node(resources, user, config, result)

    @task_tool(NodeUpdate)
    async def update_node(**values: object) -> object:
        """Atomically update supplied name/description and/or add/remove deck sense IDs.
        Null or omitted name/description means unchanged. Use clear_description=true to clear
        description. Membership changes apply
        only to decks and preserve unrelated senses. Returns actual added/removed counts.
        """
        data = NodeUpdate.model_validate(values)
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
                config.library,
            )
        return await saved_node(resources, user, config, result)

    async def batch_nodes(
        data: NodeMove | NodeCopy | NodeBatch,
        operation: Callable[[AsyncSession, UUID], Awaitable[object]],
    ) -> dict[str, object]:
        items: list[dict[str, object]] = []
        saved: list[tuple[dict[str, object], Mapping[str, object]]] = []
        for identifier in data.node_ids:
            try:
                async with resources.sessions() as session:
                    result = await operation(session, identifier)
                items.append({"source_node_id": identifier, "status": "succeeded"})
                if isinstance(result, Mapping):
                    saved.append((items[-1], cast(Mapping[str, object], result)))
            except OperationError as exc:
                logger.warning(
                    "assistant_batch_node_failed",
                    node_id=str(identifier),
                    error=exc.code,
                )
                items.append({"source_node_id": identifier, "status": "failed", "error": exc.code})
        if saved:
            enriched = await saved_nodes(resources, user, config, [r for _, r in saved])
            for (item, _), card in zip(saved, enriched, strict=True):
                item.update(card)
        return {"items": items}

    @task_tool(NodeMove)
    async def move_nodes(**values: object) -> object:
        """Move owned nodes to one folder. Each item is atomic; reports partial failures.
        Entering Published requires confirm_publication; retain_personal_reference optionally
        keeps an alias at the old location. Does not change membership or metadata.
        """
        data = NodeMove.model_validate(values)
        move = Move(**data.model_dump(exclude={"node_ids"}))
        return await batch_nodes(
            data,
            lambda session, identifier: nodes.move_node(
                session, user, identifier, move, config.library
            ),
        )

    @task_tool(NodeCopy)
    async def copy_nodes(**values: object) -> object:
        """Copy owned nodes/subtrees to one folder. Each item is atomic; returns source-to-
        new-node IDs and per-item failures. Publishing needs confirm_publication.
        """
        data = NodeCopy.model_validate(values)
        destination = NodeDestination(**data.model_dump(exclude={"node_ids"}))
        return await batch_nodes(
            data,
            lambda session, identifier: nodes.copy_node(
                session, user, identifier, destination, config.library
            ),
        )

    @task_tool(NodeBatch)
    async def delete_nodes(**values: object) -> object:
        """Delete owned normal nodes and descendants. Each item is atomic; return exact
        success/failure per node. System roots are protected; learning state is preserved.
        """
        return await batch_nodes(
            NodeBatch.model_validate(values),
            lambda session, identifier: nodes.delete_node(session, user, identifier),
        )

    def preference_projection(result: Mapping[str, object]) -> dict[str, object]:
        return {
            k: result[k]
            for k in ("settings", "effective_learning", "learning_restriction", "learning_options")
        }

    @task_tool()
    async def get_preferences(**values: object) -> object:
        """Read saved settings, effective learning selection and current plan restrictions.
        Saved typed preferences may differ from formats actually available to this user.
        """
        async with resources.sessions() as session:
            return preference_projection(await profile(user, config.account, config.study, session))

    @task_tool(PreferencesPatch)
    async def update_preferences(**values: object) -> object:
        """Update only requested settings; preserve other preferences. Return saved and
        effective learning configuration/plan restrictions. Does not change the user's plan.
        """
        filtered = {k: v for k, v in values.items() if v is not None}
        async with resources.sessions() as session:
            updated = await save_preferences(
                session,
                user,
                PreferencesPatch.model_validate(filtered),
                config.account,
                config.study,
            )
            user_profile = await profile(updated.id, config.account, config.study, session)
            return preference_projection(user_profile)

    @task_tool(WordGeneration)
    async def generate_words(**values: object) -> object:
        """Generate up to 10 entries using reference_ids from search_words. Waits for
        jobs concurrently and returns completed Word IDs and senses, or per-entry errors.
        Pending means the wait deadline expired; the job continues and is not a failure.
        """
        data = WordGeneration.model_validate(values)

        async def generate(reference_id: str) -> dict[str, object]:
            try:
                job = await request_generation(
                    resources.sessions,
                    resources.redis,
                    resources.broker,
                    config.vocabulary,
                    config.jobs,
                    user,
                    reference_id,
                )
            except OperationError as error:
                return {"reference_id": reference_id, "status": "failed", "error": error.code}
            item: dict[str, object] = {
                "reference_id": reference_id,
                **cast(dict[str, object], job.model_dump(mode="json")),
            }
            handle = AsyncTaskiqTask(str(job.job_id), resources.broker.result_backend)
            try:
                async with asyncio.timeout(config.jobs.timeout_seconds):
                    result = await handle.wait_result(
                        check_interval=1, timeout=config.jobs.timeout_seconds
                    )
            except TimeoutError, TaskiqResultTimeoutError:
                return {**item, "status": "pending"}
            except RedisError:
                return {**item, "status": "pending", "error": "job_status_unavailable"}
            if result.is_err:
                return {**item, "status": "failed", "error": "job_failed"}
            ret = result.return_value
            word_id: int | None = None
            if isinstance(ret, dict):
                raw_id = cast(dict[str, object], ret).get("word_id")
                if isinstance(raw_id, int):
                    word_id = raw_id
            if word_id is None or word_id <= 0:
                return {**item, "status": "failed", "error": "invalid_generation_result"}
            try:
                senses = (await vocabulary(resources, user, config, word_ids=[word_id]))["senses"]
            except OperationError as error:
                return {**item, "status": "failed", "error": error.code}
            return {**item, "status": "succeeded", "word_id": word_id, "senses": senses}

        return {
            "items": await asyncio.gather(
                *(generate(ref) for ref in dict.fromkeys(data.reference_ids))
            )
        }

    return [
        search_words,
        generate_words,
        read_vocabulary,
        search_nodes,
        read_library,
        learning_overview,
        create_node,
        update_node,
        move_nodes,
        copy_nodes,
        delete_nodes,
        get_preferences,
        update_preferences,
    ]
