"""A startup-built Tantivy index with serialized incremental publication."""

import asyncio
import json
from collections import defaultdict
from collections.abc import Generator, Sequence
from time import perf_counter
from typing import cast

import tantivy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.observability import get_logger
from pycil.vocabulary import models as rows
from pycil.vocabulary.enums import EntryType, GenerationState, HitKind, MatchKind
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.patterns import matches_pattern, surface_head_key
from pycil.vocabulary.references.models import ReferenceWord
from pycil.vocabulary.references.reference import encode_reference_id
from pycil.vocabulary.schemas import ReferenceHit, SearchResult, WordHit
from pycil.vocabulary.text import answer_key

logger = get_logger(__name__)


def _get_str(doc: tantivy.Document, name: str) -> str:
    return cast(str, doc[name][0])


def _get_int(doc: tantivy.Document, name: str) -> int:
    return cast(int, doc[name][0])


type SearchProjection = tuple[
    list[tuple[int, str, EntryType | None]],
    list[tuple[int, str]],
    list[tuple[int, int, str]],
    list[tuple[int, int, str, str | None]],
    set[int],
]


class SearchIndex:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions
        self.index: tantivy.Index | None = None
        self.writer: tantivy.IndexWriter | None = None
        self.snapshot: tuple[tantivy.Index, tantivy.Searcher] | None = None
        self.lock = asyncio.Lock()

    async def projection(self, word_id: int | None = None) -> SearchProjection:
        ids = select(rows.Word.id).where(rows.Word.generation_state == GenerationState.DONE)
        if word_id is not None:
            ids = ids.where(rows.Word.id == word_id)
        async with self.sessions() as session:
            words: list[tuple[int, str, EntryType | None]] = [
                (row[0], row[1], row[2])
                for row in (
                    await session.execute(
                        select(rows.Word.id, rows.Word.lemma, rows.Word.entry_type).where(
                            rows.Word.id.in_(ids)
                        )
                    )
                ).all()
            ]
            aliases: list[tuple[int, str]] = [
                (row[0], row[1])
                for row in (
                    await session.execute(
                        select(rows.WordAlias.word_id, rows.WordAlias.content).where(
                            rows.WordAlias.word_id.in_(ids)
                        )
                    )
                ).all()
            ]
            forms: list[tuple[int, int, str]] = [
                (row[0], row[1], row[2])
                for row in (
                    await session.execute(
                        select(rows.Sense.word_id, rows.SenseForm.sense_id, rows.SenseForm.surface)
                        .join(rows.Sense, rows.Sense.id == rows.SenseForm.sense_id)
                        .where(rows.Sense.word_id.in_(ids))
                    )
                ).all()
            ]
            patterns: list[tuple[int, int, str, str | None]] = [
                (row[0], row[1], row[2], row[3])
                for row in (
                    await session.execute(
                        select(
                            rows.Sense.word_id,
                            rows.SensePattern.sense_id,
                            rows.SensePattern.content,
                            rows.SensePattern.head_key,
                        )
                        .join(rows.Sense, rows.Sense.id == rows.SensePattern.sense_id)
                        .where(rows.Sense.word_id.in_(ids))
                    )
                ).all()
            ]
            consumed: set[int] = set(
                (
                    await session.scalars(
                        select(rows.WordReference.source_id).where(
                            rows.WordReference.word_id.in_(ids)
                        )
                    )
                ).all()
            )
        return words, aliases, forms, patterns, consumed

    @staticmethod
    def documents(
        projection: SearchProjection, reference: Sequence[ReferenceWord]
    ) -> Generator[tantivy.Document]:
        words, aliases, forms, patterns, consumed = projection
        entries: dict[str, tuple[int, str, EntryType | None, list[tuple[int, str]]]] = {
            f"word:{identifier}": (identifier, lemma, kind, [(0, lemma)])
            for identifier, lemma, kind in words
        }
        sense_forms: defaultdict[int, list[str]] = defaultdict(list)
        for identifier, surface in aliases:
            entries[f"word:{identifier}"][3].append((1, surface))
        for identifier, sense_id, surface in forms:
            entries[f"word:{identifier}"][3].append((2, surface))
            sense_forms[sense_id].append(surface)
        for word in reference:
            if word.id not in consumed:
                entries[f"reference:{word.id}"] = (
                    word.id,
                    word.display_form,
                    word.entry_type,
                    [
                        (0, word.lemma),
                        (0, word.display_form),
                        *[(1, pair[0]) for pair in word.alternatives],
                        *[(2, surface) for surface in word.inflections],
                    ],
                )

        def document(identity: str, rank: int, surface: str) -> tantivy.Document:
            identifier, label, kind, _surfaces = entries[identity]
            source = identity.split(":", 1)[0]
            return tantivy.Document(
                identity=identity,
                source=source,
                label=label,
                entry_type=kind.value if kind is not None else "",
                matched_surface=surface,
                identifier=identifier,
                surface_rank=rank,
                order=(
                    f"{int(source != HitKind.WORD)}{rank}{answer_key(label)}"
                    f"\0{identifier:020d}\0{answer_key(surface)}"
                ),
            )

        for identity, (_identifier, _lemma, _kind, surfaces) in entries.items():
            for rank, surface in sorted(set(surfaces)):
                doc = document(identity, rank, surface)
                doc.add_text("surface", answer_key(surface))
                yield doc
        for identifier, sense_id, pattern, head in patterns:
            identity = f"word:{identifier}"
            lemma = answer_key(entries[identity][1])
            first, _, tail = lemma.partition(" ")
            licensed = [
                value.partition(" ")[0]
                for form in sense_forms[sense_id]
                if not (value := answer_key(form)).partition(" ")[2]
                or value.partition(" ")[2] == tail
            ]
            doc = document(identity, 3, pattern)
            doc.add_text("forms", json.dumps({first: licensed}))
            for candidate_head in {
                head,
                *(surface_head_key(form) for form in sense_forms[sense_id]),
            }:
                doc.add_text("head", candidate_head or "\0")
            yield doc

    @staticmethod
    def build(
        projection: SearchProjection, reference: Sequence[ReferenceWord]
    ) -> tuple[tantivy.Index, tantivy.IndexWriter, tuple[tantivy.Index, tantivy.Searcher]]:
        builder = tantivy.SchemaBuilder()
        for name in ("identity", "source", "surface", "head"):
            builder.add_text_field(
                name, stored=name == "identity", tokenizer_name="raw", index_option="basic"
            )
        for name in ("label", "entry_type", "matched_surface", "forms"):
            builder.add_text_field(name, stored=True, tokenizer_name="raw", index_option="basic")
        builder.add_text_field("order", fast=True, tokenizer_name="raw")
        builder.add_unsigned_field("identifier", stored=True)
        builder.add_unsigned_field("surface_rank", stored=True)
        index = tantivy.Index(builder.build())
        writer = index.writer(heap_size=15_000_000, num_threads=1)
        try:
            for document in SearchIndex.documents(projection, reference):
                writer.add_document(document)
            writer.commit()
            index.reload()
            return index, writer, (index, index.searcher())
        except BaseException:
            writer.wait_merging_threads()
            raise

    async def start(self) -> None:
        async with self.lock:
            if self.snapshot is not None:
                return
            async with self.sessions() as session:
                reference = list(
                    (await session.scalars(select(ReferenceWord).order_by(ReferenceWord.id))).all()
                )
            projection = await self.projection()
            task = asyncio.create_task(asyncio.to_thread(self.build, projection, reference))
            try:
                self.index, self.writer, self.snapshot = await asyncio.shield(task)
            except asyncio.CancelledError:
                self.index, self.writer, self.snapshot = await task
                raise
            logger.info(
                "search_index_started", words=len(projection[0]), reference_words=len(reference)
            )

    async def update(self, word_id: int) -> None:
        started = perf_counter()
        async with self.lock:
            self.ready()
            assert self.writer is not None
            assert self.index is not None
            projection = await self.projection(word_id)
            writer, index = self.writer, self.index

            def publish() -> tuple[tantivy.Index, tantivy.Searcher]:
                writer.delete_documents_by_term("identity", f"word:{word_id}")
                for identifier in projection[4]:
                    writer.delete_documents_by_term("identity", f"reference:{identifier}")
                for document in self.documents(projection, []):
                    writer.add_document(document)
                writer.commit()
                index.reload()
                return index, index.searcher()

            task = asyncio.create_task(asyncio.to_thread(publish))
            try:
                self.snapshot = await asyncio.shield(task)
            except asyncio.CancelledError:
                self.snapshot = await task
                raise
            logger.info(
                "search_word_published",
                word_id=word_id,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )

    def ready(self) -> None:
        if self.snapshot is None:
            raise RuntimeError("search index is unavailable")

    @staticmethod
    def find(
        snapshot: tuple[tantivy.Index, tantivy.Searcher] | None,
        query: str,
        include_reference: bool,
        limit: int,
    ) -> list[WordHit | ReferenceHit]:
        assert snapshot is not None
        index, searcher = snapshot
        schema, key = index.schema, answer_key(query)
        ranked: dict[str, tuple[tuple[int, int, int, str, int], WordHit | ReferenceHit]] = {}

        def candidate(doc: tantivy.Document, kind: MatchKind) -> None:
            identity = _get_str(doc, "identity")
            generated = identity.startswith("word:")
            identifier = _get_int(doc, "identifier")
            label = _get_str(doc, "label")
            entry_type = EntryType(_get_str(doc, "entry_type"))
            matched_surface = _get_str(doc, "matched_surface")
            hit: WordHit | ReferenceHit = (
                WordHit(
                    word_id=identifier,
                    lemma=label,
                    entry_type=entry_type,
                    match_kind=kind,
                    matched_surface=matched_surface,
                )
                if generated
                else ReferenceHit(
                    reference_id=encode_reference_id(identifier),
                    display=label,
                    entry_type=entry_type,
                    match_kind=kind,
                    matched_surface=matched_surface,
                )
            )
            order = (
                tuple(MatchKind).index(kind),
                int(not generated),
                _get_int(doc, "surface_rank"),
                answer_key(label),
                identifier,
            )
            if identity not in ranked or order < ranked[identity][0]:
                ranked[identity] = (order, hit)

        literal = "".join("\\" + char if char in r"\.^$|?*+(){}[]" else char for char in key)
        branches: list[tuple[MatchKind, tantivy.Query]] = [
            (MatchKind.EXACT, tantivy.Query.term_query(schema, "surface", key)),
            (MatchKind.PREFIX, tantivy.Query.regex_query(schema, "surface", literal + ".*")),
            (
                MatchKind.SUBSTRING,
                tantivy.Query.regex_query(schema, "surface", ".*" + literal + ".*"),
            ),
        ]
        if len(key) >= 3:
            branches.append(
                (
                    MatchKind.FUZZY,
                    tantivy.Query.fuzzy_term_query(
                        schema, "surface", key, distance=1 if len(key) < 6 else 2
                    ),
                )
            )
        for kind, branch in branches:
            if kind is MatchKind.PREFIX:
                heads = tantivy.Query.boolean_query(
                    [
                        (tantivy.Occur.Should, tantivy.Query.term_query(schema, "head", head))
                        for head in {surface_head_key(key), "\0"}
                    ]
                )
                total: int = int(getattr(searcher.search(heads, limit=1), "count", 0))
                if total and sum(order[1] == 0 for order, _hit in ranked.values()) < limit:
                    prefix_search = searcher.search(heads, limit=total, count=False)
                    for hit_tuple in prefix_search.hits:
                        address = hit_tuple[1]
                        doc = searcher.doc(address)
                        if _get_str(doc, "identity") not in ranked and matches_pattern(
                            _get_str(doc, "matched_surface"),
                            query,
                            forms=cast(dict[str, list[str]], json.loads(_get_str(doc, "forms"))),
                        ):
                            candidate(doc, MatchKind.EXACT)
            if kind is not MatchKind.EXACT and len(ranked) >= limit:
                break
            combined = tantivy.Query.const_score_query(branch, 1.0)
            if not include_reference:
                combined = tantivy.Query.boolean_query(
                    [
                        (tantivy.Occur.Must, combined),
                        (
                            tantivy.Occur.Must,
                            tantivy.Query.term_query(schema, "source", HitKind.WORD.value),
                        ),
                    ]
                )
            fetched, size, seen = 0, limit, set[str]()
            while len(seen) < limit:
                search_res = searcher.search(
                    combined,
                    limit=size,
                    count=False,
                    order_by_field="order",
                    order=tantivy.Order.Asc,
                )
                hits = search_res.hits
                for hit_tuple in hits[fetched:]:
                    address = hit_tuple[1]
                    doc = searcher.doc(address)
                    identity = _get_str(doc, "identity")
                    if identity not in seen:
                        seen.add(identity)
                        candidate(doc, kind)
                    if len(seen) >= limit:
                        break
                if len(hits) < size:
                    break
                fetched, size = size, size * 2
        return [hit for _order, hit in sorted(ranked.values(), key=lambda item: item[0])[:limit]]

    async def search(
        self, query: str, include_reference: bool = False, *, limit: int = 30
    ) -> SearchResult:
        if not query.strip() or len(query) > 256 or type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidResourceError("invalid lexical query")
        self.ready()
        values = await asyncio.to_thread(self.find, self.snapshot, query, include_reference, limit)
        return SearchResult(items=values)

    async def close(self) -> None:
        async with self.lock:
            self.snapshot = None
            writer, self.writer = self.writer, None
            self.index = None
            if writer is not None:
                await asyncio.to_thread(writer.wait_merging_threads)
