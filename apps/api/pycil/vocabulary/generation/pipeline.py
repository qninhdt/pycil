import asyncio
from dataclasses import dataclass
from typing import Protocol, Self

from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.cache import MemoryCache
from pycil.infrastructure.content_revisions import GRAPH_KEY, capture, publish
from pycil.infrastructure.database import transaction_lock
from pycil.infrastructure.llm import render_prompt
from pycil.infrastructure.observability import get_logger, observe_operation
from pycil.vocabulary import models as rows
from pycil.vocabulary.enums import (
    GenerationState,
    HitKind,
    MatchKind,
    ReferenceSource,
    SenseRelationType,
    WordRelationType,
    normalize_pos,
)
from pycil.vocabulary.errors import InvalidOutputError, InvalidResourceError
from pycil.vocabulary.generation.schemas import (
    Enrichment,
    EnrichmentBatch,
    Inventory,
    InventorySense,
    validate_inventory,
)
from pycil.vocabulary.patterns import pattern_head_key, surface_head_key
from pycil.vocabulary.references.models import SourceWord
from pycil.vocabulary.references.reference import fetch_reference
from pycil.vocabulary.references.wordnet import lookup
from pycil.vocabulary.schemas import CachedWord, SearchResult, Sense
from pycil.vocabulary.schemas import Word as WordSchema
from pycil.vocabulary.text import (
    answer_key,
    marked_occurrences,
    match_key,
    parse_form,
    target_sequences,
    validate_lemma,
)
from pycil.vocabulary.words import (
    consumed_word,
    get_word,
    link_reference,
    publish_identity,
    target_words,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class _TempForm:
    surface: str


@dataclass(frozen=True)
class _TempSense:
    forms: list[_TempForm]


class SearchProtocol(Protocol):
    async def search(
        self, query: str, include_reference: bool = False, *, limit: int = 30
    ) -> SearchResult: ...
    async def update(self, word_id: int) -> None: ...


class StructuredLLMProtocol(Protocol):
    async def complete[T: BaseModel](self, instruction: str, data: str, schema: type[T]) -> T: ...


async def generate_word(
    sessions: async_sessionmaker[AsyncSession],
    search: SearchProtocol,
    structured_llm: StructuredLLMProtocol,
    word_cache: MemoryCache[int, CachedWord],
    target: str,
    *,
    sense_cache: MemoryCache[int, Sense] | None = None,
    reference_id: str | None = None,
    example_count: int,
    enrichment_batch_size: int,
) -> WordSchema:
    with observe_operation(logger, "word_generation", reference_id=reference_id):
        target = validate_lemma(target)
        if type(example_count) is not int or example_count < 1:
            raise ValueError("invalid example count")
        if type(enrichment_batch_size) is not int or not 1 <= enrichment_batch_size <= 8:
            raise ValueError("invalid enrichment batch size")
        if reference_id is None:
            result = await search.search(target, include_reference=True)
            hit = result.items[0] if result.items else None
            if hit is None or hit.match_kind is not MatchKind.EXACT:
                raise InvalidResourceError("no exact lexical match")
            if hit.kind is HitKind.WORD:
                word = await get_word(
                    sessions, hit.word_id, word_cache=word_cache, sense_cache=sense_cache
                )
                if word is None:
                    raise InvalidResourceError("matched word is unavailable")
                return word
            reference_id = hit.reference_id
            try:
                target = validate_lemma(hit.display)
            except ValueError:
                pass
        source = await fetch_reference(sessions, reference_id)
        async with sessions() as session:
            identifier = await consumed_word(session, source.id)
        if identifier is None:
            identifier = await _generate(
                sessions, structured_llm, source, target, example_count, enrichment_batch_size
            )
        word_cache.clear()
        if sense_cache is not None:
            sense_cache.clear()
        await search.update(identifier)
        word = await get_word(sessions, identifier, word_cache=word_cache, sense_cache=sense_cache)
        if word is None:
            raise InvalidResourceError("published word is unavailable")
        logger.info("word_publication_completed", word_id=identifier, reference_word_id=source.id)
        return word


async def _generate(
    sessions: async_sessionmaker[AsyncSession],
    structured_llm: StructuredLLMProtocol,
    source: SourceWord,
    target: str,
    example_count: int,
    enrichment_batch_size: int,
) -> int:
    supporting = await lookup(target)
    citations: dict[str, tuple[ReferenceSource, str]] = {}
    references: list[dict[str, str]] = []
    for position, sense in enumerate(source.senses, 1):
        key = f"a{position}"
        citations[key] = ReferenceSource.REFERENCE, str(sense.id)
        item = dict(
            id=key,
            pos=normalize_pos(sense.pos) or sense.pos or "unknown",
            definition=sense.definition,
        )
        if sense.headword and sense.headword != target:
            item["headword"] = sense.headword
        if sense.phrase_title:
            item["phrasal"] = sense.phrase_title
        references.append(item)
    for position, sense in enumerate(supporting, 1):
        key = f"b{position}"
        citations[key] = ReferenceSource.WORDNET, sense["key"]
        references.append(
            dict(
                id=key, pos=normalize_pos(sense["pos"]) or "unknown", definition=sense["definition"]
            )
        )
    grouped: dict[str, list[dict[str, str]]] = {}
    for reference in references:
        pos = reference.pop("pos")
        if pos not in grouped:
            grouped[pos] = []
        grouped[pos].append(reference)
    instruction, data = render_prompt(
        "vocabulary/generation/prompts/inventory.jinja", target=target, references=grouped
    )

    class GroundedInventory(Inventory):
        @model_validator(mode="after")
        def supplied_evidence(self) -> Self:
            validate_inventory(self, set(citations))
            return self

    try:
        inventory = GroundedInventory.model_validate(
            await structured_llm.complete(instruction, data, GroundedInventory)
        )
    except ValueError:
        raise InvalidOutputError("invalid word inventory evidence") from None
    # Reuse an already completed canonical word before buying enrichment calls.
    async with sessions() as session, session.begin():
        await transaction_lock(session, GRAPH_KEY)
        await transaction_lock(session, "word:" + match_key(inventory.lemma))
        existing = await session.scalar(
            select(rows.Word)
            .where(
                rows.Word.match_key == match_key(inventory.lemma),
                rows.Word.generation_state == GenerationState.DONE,
            )
            .with_for_update()
        )
        if existing is not None:
            before = await capture(session, [("word", existing.id)])
            await link_reference(session, existing.id, source.id)
            await publish(session, before)
            return existing.id

    async def enrich(batch: list[tuple[int, InventorySense]]) -> list[Enrichment]:
        class GroundedEnrichment(EnrichmentBatch):
            @model_validator(mode="after")
            def supplied_senses(self) -> Self:
                if {sense.sense_id for sense in self.senses} != {index for index, _seed in batch}:
                    raise ValueError("enrichment changed the supplied sense identities")
                for detail in self.senses:
                    forms = [_TempForm(surface=parse_form(form)[0]) for form in detail.forms]
                    sequences = target_sequences(inventory, _TempSense(forms=forms))
                    for example in detail.examples:
                        try:
                            marked_occurrences(example, sequences)
                        except InvalidOutputError as error:
                            raise ValueError(str(error)) from error
                return self

        instruction, data = render_prompt(
            "vocabulary/generation/prompts/enrich_sense.jinja",
            word=dict(lemma=inventory.lemma, type=inventory.type, aliases=inventory.aliases),
            senses=[
                dict(sense_id=index, definition=seed.definition, pos=seed.pos)
                for index, seed in batch
            ],
            examples_per_sense=example_count,
        )
        try:
            result = GroundedEnrichment.model_validate(
                await structured_llm.complete(instruction, data, GroundedEnrichment)
            )
        except ValueError:
            raise InvalidOutputError("invalid enrichment evidence") from None
        return result.senses

    seeds: list[tuple[int, InventorySense]] = list(enumerate(inventory.senses, 1))
    tasks: list[asyncio.Task[list[Enrichment]]] = [
        asyncio.create_task(enrich(seeds[offset : offset + enrichment_batch_size]))
        for offset in range(0, len(seeds), enrichment_batch_size)
    ]
    try:
        details: dict[int, Enrichment] = {
            item.sense_id: item for result in await asyncio.gather(*tasks) for item in result
        }
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    async with sessions() as session, session.begin():
        await transaction_lock(session, GRAPH_KEY)
        word, before = await publish_identity(
            session, source.id, inventory.lemma, inventory.type, inventory.aliases
        )
        if word.generation_state == GenerationState.DONE:
            await publish(session, before)
            return word.id
        groups: list[tuple[rows.Sense, InventorySense, Enrichment]] = []
        for index, seed in seeds:
            detail = details[index]
            pronunciation = next(
                (
                    sense
                    for position, sense in enumerate(source.senses, 1)
                    if f"a{position}" in seed.references and normalize_pos(sense.pos) == seed.pos
                ),
                None,
            )
            sense = rows.Sense(
                word_id=word.id,
                pos=seed.pos,
                tier=detail.tier,
                cefr_level=detail.cefr_level,
                register=detail.register_,
                ipa_uk=pronunciation.ipa_uk if pronunciation else None,
                ipa_us=pronunciation.ipa_us if pronunciation else None,
            )
            session.add(sense)
            groups.append((sense, seed, detail))
        await session.flush()
        word_edges: list[tuple[str, WordRelationType]] = [
            (lemma, group.type) for group in inventory.related for lemma in group.lemmas
        ]
        for reference in source.senses:
            if reference.phrase_title:
                try:
                    word_edges.append(
                        (
                            validate_lemma(reference.phrase_title),
                            WordRelationType.PART_OF_PHRASAL_FAMILY,
                        )
                    )
                except ValueError:
                    pass
        sense_edges: list[tuple[int, str, SenseRelationType]] = [
            (sense.id, lemma, group.type)
            for sense, _seed, detail in groups
            for group in detail.relations
            for lemma in group.lemmas
        ]
        targets, created = await target_words(
            session,
            [lemma for lemma, _kind in word_edges] + [lemma for _id, lemma, _kind in sense_edges],
        )
        before.update(created)
        for sense, seed, detail in groups:
            session.add(rows.Definition(sense_id=sense.id, content=seed.definition))
            session.add_all(
                rows.Example(sense_id=sense.id, content=content) for content in detail.examples
            )
            for form in detail.forms:
                surface, inflection = parse_form(form)
                session.add(
                    rows.SenseForm(
                        sense_id=sense.id,
                        surface=surface,
                        inf=inflection,
                        match_key=answer_key(surface),
                        head_key=surface_head_key(surface),
                    )
                )
            session.add_all(
                rows.SensePattern(
                    sense_id=sense.id, content=pattern, head_key=pattern_head_key(pattern)
                )
                for pattern in detail.patterns
            )
            session.add_all(
                rows.Collocation(sense_id=sense.id, content=content)
                for content in detail.collocations
            )
            session.add_all(
                rows.SenseReference(
                    sense_id=sense.id, source=citations[key][0], source_ref=citations[key][1]
                )
                for key in seed.references
            )
        word_relations = [
            rows.WordRelation(from_word_id=word.id, to_word_id=identifier, rel_type=kind)
            for identifier, kind in set(
                (targets[match_key(lemma)], kind) for lemma, kind in word_edges
            )
            if identifier != word.id
        ]
        session.add_all(word_relations)
        sense_relations = [
            rows.SenseRelation(from_sense_id=sense_id, to_word_id=identifier, rel_type=kind)
            for sense_id, identifier, kind in set(
                (sense_id, targets[match_key(lemma)], kind) for sense_id, lemma, kind in sense_edges
            )
        ]
        session.add_all(sense_relations)
        word.generation_state = GenerationState.DONE
        await session.flush()
        await publish(session, before)
        identifier = word.id
    return identifier
