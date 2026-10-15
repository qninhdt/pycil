import pytest
from sqlalchemy import func, select

from pycil.app.config import load_config
from pycil.infrastructure.cache import MemoryCache
from pycil.vocabulary.enums import GenerationStage, GenerationState, HitKind, JobState, MatchKind
from pycil.vocabulary.errors import InvalidOutputError
from pycil.vocabulary.generation.jobs import Generations
from pycil.vocabulary.generation.pipeline import generate_word
from pycil.vocabulary.models import Sense, SenseReference, Word
from pycil.vocabulary.references.importer import import_reference
from pycil.vocabulary.references.reference import encode_reference_id
from pycil.vocabulary.search import SearchIndex
from tests.support.inference import WordProvider
from tests.support.reference import reference_file, reference_word


async def test_generation_publishes_content_and_consumes_reference_search_hit(database, tmp_path):
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    index, provider, cache = (
        SearchIndex(database.sessions),
        WordProvider(),
        MemoryCache(max_entries=1024, ttl=30),
    )
    try:
        await index.start()
        before = await index.search("bank", include_reference=True)
        assert before.items[0].kind is HitKind.REFERENCE
        word = await generate_word(
            database.sessions,
            index,
            provider,
            cache,
            "bank",
            reference_id=encode_reference_id(1),
            example_count=1,
            enrichment_batch_size=8,
        )
        assert word.senses[0].definition.content == "a financial institution"
        assert word.senses[0].ipa_uk == "bæŋk"
        assert word.senses[0].examples[0].content == "The [bank] opens at nine."
        assert word.senses[0].cefr_level.value == "a2"
        assert word.related[0].rel_type.value == "word_family"
        assert word.related[0].to_word_lemma == "banking"
        assert word.senses[0].relations[0].rel_type.value == "synonym"
        assert word.senses[0].relations[0].to_word_lemma == "lender"
        after = await index.search("bank", include_reference=True)
        assert after.items[0].kind is HitKind.WORD
        assert all(item.kind is not HitKind.REFERENCE for item in after.items)
        inflected = await index.search("banks")
        assert inflected.items[0].word_id == word.id
        assert inflected.items[0].match_kind is MatchKind.EXACT
        reused = await generate_word(
            database.sessions,
            index,
            provider,
            cache,
            "bank",
            reference_id=encode_reference_id(1),
            example_count=1,
            enrichment_batch_size=8,
        )
        assert reused.id == word.id
        assert provider.calls == 2
        async with database.sessions() as session:
            citation = await session.scalar(select(SenseReference))
            assert citation.source.value == "reference"
            assert citation.source_ref == "101"
    finally:
        await index.close()


@pytest.mark.parametrize(
    "defect,feedback",
    [
        ("citation", "evidence that was not supplied"),
        ("identity", "supplied sense identities"),
        ("target", "fixed lexical components"),
    ],
)
async def test_native_instructor_reasks_for_semantic_defects_before_publication(
    database, tmp_path, defect, feedback
):
    import json

    import httpx

    from pycil.infrastructure.llm import StructuredLLM
    from pycil.vocabulary.generation.schemas import EnrichmentBatch, Inventory

    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    provider = WordProvider()
    inventory = (await provider.complete("", "", Inventory)).model_dump(mode="json")
    enrichment = (await provider.complete("", "", EnrichmentBatch)).model_dump(
        mode="json", by_alias=True
    )
    requests, repaired = [], False

    async def respond(request):
        nonlocal repaired
        body = json.loads(request.content)
        requests.append(body)
        is_inventory = body["response_format"]["json_schema"]["name"] == "GroundedInventory"
        payload = json.loads(json.dumps(inventory if is_inventory else enrichment))
        if not repaired and is_inventory == (defect == "citation"):
            repaired = True
            if defect == "citation":
                payload["senses"][0]["references"] = ["missing"]
            elif defect == "identity":
                payload["senses"][0]["sense_id"] = 99
            else:
                payload["senses"][0]["examples"] = ["The [river] opens."]
        return httpx.Response(
            200,
            json={
                "id": "generation",
                "object": "chat.completion",
                "created": 0,
                "model": "provider-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(payload)},
                    }
                ],
            },
        )

    index = SearchIndex(database.sessions)
    try:
        await index.start()
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            policy = load_config().runtime.providers.vocabulary.model_copy(
                update={"max_retries": 1}
            )
            llm = StructuredLLM(
                policy, api_key="test", base_url="https://provider.test", http_client=http
            )
            word = await generate_word(
                database.sessions,
                index,
                llm,
                MemoryCache(max_entries=1024, ttl=30),
                "bank",
                example_count=1,
                enrichment_batch_size=8,
            )
        assert word.senses[0].examples[0].content == "The [bank] opens at nine."
        assert len(requests) == 3
        retry = requests[1 if defect == "citation" else 2]
        assert feedback in retry["messages"][-1]["content"]
    finally:
        await index.close()


async def test_index_failure_keeps_committed_content_and_retry_reuses_it(
    database, tmp_path, monkeypatch, redis_store
):
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    index, provider, cache = (
        SearchIndex(database.sessions),
        WordProvider(),
        MemoryCache(max_entries=1024, ttl=30),
    )

    redis, namespace = redis_store
    jobs = Generations(
        database.sessions,
        index,
        provider,
        cache,
        load_config(),
        redis=redis,
        prefix=namespace + ":word-tasks",
    )

    async def failed_update(word_id):
        raise RuntimeError("private index error")

    try:
        await index.start()
        with monkeypatch.context() as patch:
            patch.setattr(index, "update", failed_update)
            submitted = await jobs.submit("bank", reference_id=encode_reference_id(1))
            await jobs.wait([submitted["task_id"]])
            failed = await jobs.status(submitted["task_id"])
            assert failed["status"] is JobState.FAILED
            assert failed["stage"] is not GenerationStage.READY
            assert failed["error"] == "generation_failed"
        async with database.sessions() as session:
            persisted = await session.scalar(select(Word).where(Word.lemma == "bank"))
            assert persisted.generation_state is GenerationState.DONE
            word_id = persisted.id
            assert await session.scalar(select(func.count()).select_from(Sense)) == 1
        retry = await jobs.submit("bank", reference_id=encode_reference_id(1))
        await jobs.wait([retry["task_id"]])
        completed = await jobs.status(retry["task_id"])
        assert completed["status"] is JobState.SUCCEEDED
        assert completed["stage"] is GenerationStage.READY
        assert completed["word_id"] == word_id
        assert provider.calls == 2
        found = (await index.search("bank", include_reference=True)).items
        assert found[0].word_id == word_id
        assert all(item.kind is HitKind.WORD for item in found)
    finally:
        await jobs.close()
        await index.close()


async def test_assistant_generation_tools_share_status_and_reuse_content(database, redis_store):
    from types import SimpleNamespace

    from pycil.assistant.tools import tools
    from tests.support.account import account
    from tests.support.vocabulary import neutral_word

    user, _ = await account(database.sessions)
    word_id, sense_id = await neutral_word(database.sessions)
    config = load_config()
    redis, namespace = redis_store
    store = redis
    index, provider, cache = (
        SearchIndex(database.sessions),
        WordProvider(),
        MemoryCache(max_entries=1024, ttl=30),
    )
    owner = Generations(
        database.sessions,
        index,
        provider,
        cache,
        config,
        redis=store,
        prefix=namespace + ":word-tasks",
    )
    observer = Generations(
        database.sessions,
        index,
        provider,
        cache,
        config,
        redis=store,
        prefix=namespace + ":word-tasks",
    )

    def surface(generations):
        resources = SimpleNamespace(
            sessions=database.sessions, sense_cache=MemoryCache(1024, 30), generations=generations
        )
        return {tool.name: tool for tool in tools(resources, user.id, config)}

    try:
        await index.start()
        generated = await surface(owner)["generate_words"].ainvoke({"words": ["bank"]})
        item = generated["items"][0]
        assert item["status"] == "succeeded" and item["word_id"] == word_id
        assert item["senses"][0]["sense_id"] == sense_id
        polled = await surface(observer)["get_generations"].ainvoke({"task_ids": [item["task_id"]]})
        assert polled["items"][0] == {key: value for key, value in item.items() if key != "target"}
        assert not observer.flights and provider.calls == 0
    finally:
        await owner.close()
        await observer.close()
        await index.close()


async def test_invented_citation_never_publishes_word_or_sense(database, tmp_path):
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    index = SearchIndex(database.sessions)
    try:
        await index.start()
        with pytest.raises(InvalidOutputError):
            await generate_word(
                database.sessions,
                index,
                WordProvider(invalid_citation=True),
                MemoryCache(max_entries=1024, ttl=30),
                "bank",
                reference_id=encode_reference_id(1),
                example_count=1,
                enrichment_batch_size=8,
            )
        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Word)) == 0
            assert await session.scalar(select(func.count()).select_from(Sense)) == 0
        assert (await index.search("bank", include_reference=True)).items[
            0
        ].kind is HitKind.REFERENCE
    finally:
        await index.close()


async def test_enrichment_cannot_publish_examples_marked_for_another_word(database, tmp_path):
    class WrongTarget(WordProvider):
        async def complete(self, instruction, data, schema):
            result = await super().complete(instruction, data, schema)
            if schema.__name__ == "GroundedEnrichment":
                result.senses[0].examples = ["The [moon] opens at nine."]
            return result

    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    search = SearchIndex(database.sessions)
    await search.start()
    try:
        with pytest.raises(InvalidOutputError):
            await generate_word(
                database.sessions,
                search,
                WrongTarget(),
                MemoryCache(max_entries=1024, ttl=30),
                "bank",
                example_count=1,
                enrichment_batch_size=8,
            )
        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Word)) == 0
            assert await session.scalar(select(func.count()).select_from(Sense)) == 0
        assert (await search.search("bank", True)).items[0].kind == "reference"
    finally:
        await search.close()


async def test_enrichment_failure_cancels_sibling_batches_and_publishes_nothing(database, tmp_path):
    import asyncio
    import json

    from pycil.vocabulary.generation.schemas import Inventory

    sibling_started, sibling_cleaned = asyncio.Event(), asyncio.Event()

    class FailingBatch(WordProvider):
        async def complete(self, instruction, data, schema):
            if issubclass(schema, Inventory):
                return schema(
                    lemma="bank",
                    type="word",
                    aliases=[],
                    related=[],
                    senses=[
                        dict(definition=f"financial meaning {i}", pos="noun", references=["a1"])
                        for i in range(9)
                    ],
                )
            values = json.loads(data.split("<sense_request>")[1].split("</sense_request>")[0])
            if values["senses"][0]["sense_id"] == 9:
                await sibling_started.wait()
                raise RuntimeError("enrichment unavailable")
            sibling_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                sibling_cleaned.set()

    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    index = SearchIndex(database.sessions)
    await index.start()
    try:
        with pytest.raises(RuntimeError, match="enrichment unavailable"):
            async with asyncio.timeout(5):
                await generate_word(
                    database.sessions,
                    index,
                    FailingBatch(),
                    MemoryCache(max_entries=1024, ttl=30),
                    "bank",
                    example_count=1,
                    enrichment_batch_size=8,
                )
        assert sibling_cleaned.is_set()
        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Word)) == 0
            assert await session.scalar(select(func.count()).select_from(Sense)) == 0
    finally:
        await index.close()
