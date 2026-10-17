import pytest
from sqlalchemy import func, select

from pycil.app.config import load_config
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.vocabulary.enums import HitKind, MatchKind
from pycil.vocabulary.errors import InvalidOutputError
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
        SearchIndex(
            database.sessions,
            policy=load_config().vocabulary.search_runtime,
            query_policy=load_config().vocabulary.search,
        ),
        WordProvider(),
        InMemoryStore(max_entries=1024, ttl=30),
    )
    try:
        await index.start()
        before = await index.search("bank", include_reference=True)
        assert before.items[0].kind is HitKind.REFERENCE
        word = await generate_word(
            database.sessions,
            provider,
            cache,
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
        await index.update(word.id)
        after = await index.search("bank", include_reference=True)
        assert after.items[0].kind is HitKind.WORD
        assert all(item.kind is not HitKind.REFERENCE for item in after.items)
        inflected = await index.search("banks")
        assert inflected.items[0].word_id == word.id
        assert inflected.items[0].match_kind is MatchKind.EXACT
        reused = await generate_word(
            database.sessions,
            provider,
            cache,
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

    index = SearchIndex(
        database.sessions,
        policy=load_config().vocabulary.search_runtime,
        query_policy=load_config().vocabulary.search,
    )
    try:
        await index.start()
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            policy = load_config().vocabulary.provider.model_copy(
                update={"max_retries": 1}
            )
            llm = StructuredLLM(
                policy, api_key="test", base_url="https://provider.test", http_client=http
            )
            word = await generate_word(
                database.sessions,
                llm,
                InMemoryStore(max_entries=1024, ttl=30),
                reference_id=encode_reference_id(1),
                example_count=1,
                enrichment_batch_size=8,
            )
        assert word.senses[0].examples[0].content == "The [bank] opens at nine."
        assert len(requests) == 3
        retry = requests[1 if defect == "citation" else 2]
        assert feedback in retry["messages"][-1]["content"]
    finally:
        await index.close()


async def test_invented_citation_never_publishes_word_or_sense(database, tmp_path):
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    index = SearchIndex(
        database.sessions,
        policy=load_config().vocabulary.search_runtime,
        query_policy=load_config().vocabulary.search,
    )
    try:
        await index.start()
        with pytest.raises(InvalidOutputError):
            await generate_word(
                database.sessions,
                WordProvider(invalid_citation=True),
                InMemoryStore(max_entries=1024, ttl=30),
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
    search = SearchIndex(
        database.sessions,
        policy=load_config().vocabulary.search_runtime,
        query_policy=load_config().vocabulary.search,
    )
    await search.start()
    try:
        with pytest.raises(InvalidOutputError):
            await generate_word(
                database.sessions,
                WrongTarget(),
                InMemoryStore(max_entries=1024, ttl=30),
                reference_id=encode_reference_id(1),
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
    index = SearchIndex(
        database.sessions,
        policy=load_config().vocabulary.search_runtime,
        query_policy=load_config().vocabulary.search,
    )
    await index.start()
    try:
        with pytest.raises(RuntimeError, match="enrichment unavailable"):
            async with asyncio.timeout(5):
                await generate_word(
                    database.sessions,
                    FailingBatch(),
                    InMemoryStore(max_entries=1024, ttl=30),
                    reference_id=encode_reference_id(1),
                    example_count=1,
                    enrichment_batch_size=8,
                )
        assert sibling_cleaned.is_set()
        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Word)) == 0
            assert await session.scalar(select(func.count()).select_from(Sense)) == 0
    finally:
        await index.close()
