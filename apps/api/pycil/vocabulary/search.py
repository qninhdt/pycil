"""A Tantivy index shared on disk by API processes, with serialized incremental publication."""

import asyncio
import fcntl
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Sequence
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import orjson
import tantivy
from sqlalchemy import Select, func, select
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
# Bump whenever fields or document contents change; a new directory forces a rebuild.
SCHEMA_VERSION = 2
BATCH = 2_000
MATCH_KIND_ORDER = {
    MatchKind.EXACT: 0,
    MatchKind.PREFIX: 1,
    MatchKind.SUBSTRING: 2,
    MatchKind.FUZZY: 3,
}


def _schema() -> tantivy.Schema:
    """Index only what queries match or sort on; hit display data lives in one stored payload."""
    builder = tantivy.SchemaBuilder()
    for name in ("identity", "source", "surface", "head", "order", "trigram"):
        builder.add_text_field(
            name, fast=name == "order", tokenizer_name="raw", index_option="basic"
        )
    builder.add_bytes_field("payload", stored=True, indexed=False)
    builder.add_unsigned_field("identifier", fast=True)
    return builder.build()


def _trigrams(value: str) -> set[str]:
    return {value[position : position + 3] for position in range(len(value) - 2)}


def _payload(doc: tantivy.Document) -> list[Any]:
    """`[identity, label, entry_type, matched_surface, surface_rank, forms | None]`."""
    return cast(list[Any], orjson.loads(cast(bytes, doc["payload"][0])))


async def _native[T](call: Callable[[], T]) -> T:
    """Run native index work off-loop and join it on cancellation, never abandoning a writer."""
    task = asyncio.create_task(asyncio.to_thread(call))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


type SearchProjection = tuple[
    list[tuple[int, str, EntryType | None]],
    list[tuple[int, str]],
    list[tuple[int, int, str]],
    list[tuple[int, int, str, str | None]],
    set[int],
]


class SearchIndex:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], path: str | None = None) -> None:
        self.sessions = sessions
        self.path = path
        self.snapshot: tantivy.Index | None = None
        self.lock = asyncio.Lock()

    async def projection(self, first: int, last: int) -> SearchProjection:
        async with self.sessions() as session:
            words: list[tuple[int, str, EntryType | None]] = [
                (row[0], row[1], row[2])
                for row in (
                    await session.execute(
                        select(rows.Word.id, rows.Word.lemma, rows.Word.entry_type).where(
                            rows.Word.generation_state == GenerationState.DONE,
                            rows.Word.id.between(first, last),
                        )
                    )
                ).all()
            ]
            # Freeze membership: another process may finish a pending word between queries.
            word_ids = [identifier for identifier, _lemma, _kind in words]
            aliases: list[tuple[int, str]] = [
                (row[0], row[1])
                for row in (
                    await session.execute(
                        select(rows.WordAlias.word_id, rows.WordAlias.content).where(
                            rows.WordAlias.word_id.in_(word_ids)
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
                        .where(rows.Sense.word_id.in_(word_ids))
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
                        .where(rows.Sense.word_id.in_(word_ids))
                    )
                ).all()
            ]
            consumed: set[int] = set(
                (
                    await session.scalars(
                        select(rows.WordReference.source_id).where(
                            rows.WordReference.word_id.in_(word_ids)
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

        def document(
            identity: str, rank: int, surface: str, forms: dict[str, list[str]] | None = None
        ) -> tantivy.Document:
            identifier, label, kind, _surfaces = entries[identity]
            source = identity.split(":", 1)[0]
            doc = tantivy.Document(
                identity=identity,
                source=source,
                order=(
                    f"{int(source != HitKind.WORD)}{rank}{answer_key(label)}"
                    f"\0{identifier:020d}\0{answer_key(surface)}"
                ),
            )
            entry_type = kind.value if kind is not None else ""
            doc.add_bytes(
                "payload", orjson.dumps([identity, label, entry_type, surface, rank, forms])
            )
            return doc

        for identity, (_identifier, _lemma, _kind, surfaces) in entries.items():
            for rank, surface in sorted(set(surfaces)):
                doc = document(identity, rank, surface)
                key = answer_key(surface)
                doc.add_text("surface", key)
                for trigram in _trigrams(key):
                    doc.add_text("trigram", trigram)
                yield doc
        for identifier, sense_id, pattern, head in patterns:
            identity = f"word:{identifier}"
            lemma = answer_key(entries[identity][1])
            first, _, tail = lemma.partition(" ")
            licensed = []
            for form in sense_forms[sense_id]:
                form_head, _, form_tail = answer_key(form).partition(" ")
                if not form_tail or form_tail == tail:
                    licensed.append(form_head)
            doc = document(identity, 3, pattern, {first: licensed})
            for candidate_head in {
                head,
                *(surface_head_key(form) for form in sense_forms[sense_id]),
            }:
                doc.add_text("head", candidate_head or "\0")
            yield doc

        for identifier, _lemma, _kind in words:
            doc = tantivy.Document(identity=f"word:{identifier}", source="word_meta")
            doc.add_unsigned("identifier", identifier)
            yield doc
        if words:
            for identifier in consumed:
                yield tantivy.Document(identity=f"reference:{identifier}", source="consumed_meta")

    def open(self) -> tantivy.Index:
        if self.path is None:
            index = tantivy.Index(_schema())
        else:
            root = Path(self.path)
            root.mkdir(parents=True, exist_ok=True)
            with (root / f"v{SCHEMA_VERSION}.lock").open("a") as guard:
                fcntl.flock(guard, fcntl.LOCK_EX)  # concurrent first boots create it once
                directory = root / f"v{SCHEMA_VERSION}"
                directory.mkdir(exist_ok=True)
                index = tantivy.Index(_schema(), path=str(directory), reuse=True)
        # Readers follow commits from any process; the publishing process also reloads at once.
        index.config_reader(reload_policy="OnCommit")
        return index

    @staticmethod
    async def lease(index: tantivy.Index) -> tantivy.IndexWriter:
        """Tantivy's lockfile admits one writer across processes; wait for the holder."""
        while True:
            try:
                return index.writer(heap_size=15_000_000, num_threads=1)
            except ValueError as error:
                if "LockBusy" not in str(error):
                    raise
            await asyncio.sleep(0.1)

    async def fingerprint(self) -> bytes:
        # shortcut: counts/max IDs miss in-place edits that bypass `update`; delete the index
        # directory to force a rebuild, or add a per-row version column if that recurs.
        async with self.sessions() as session:
            values = [
                list((await session.execute(statement)).one())
                for statement in (
                    select(func.count(), func.max(rows.Word.id)).where(
                        rows.Word.generation_state == GenerationState.DONE
                    ),
                    select(func.count(), func.max(ReferenceWord.id)),
                    select(func.count())
                    .select_from(rows.WordReference)
                    .join(rows.Word, rows.Word.id == rows.WordReference.word_id)
                    .where(rows.Word.generation_state == GenerationState.DONE),
                )
            ]
        return orjson.dumps(values)

    @staticmethod
    def stored_fingerprint(index: tantivy.Index) -> bytes | None:
        index.reload()
        searcher = index.searcher()
        hits = searcher.search(tantivy.Query.term_query(index.schema, "identity", "meta"), 1).hits
        if not hits:
            return None
        references = orjson.loads(cast(bytes, searcher.doc(hits[0][1])["payload"][0]))
        words = searcher.search(
            tantivy.Query.term_query(index.schema, "source", "word_meta"),
            1,
            order_by_field="identifier",
            order=tantivy.Order.Desc,
        )
        consumed = searcher.search(
            tantivy.Query.term_query(index.schema, "source", "consumed_meta"), 1
        ).count
        return orjson.dumps(
            [[words.count, words.hits[0][0] if words.hits else None], references, [consumed]]
        )

    @staticmethod
    def meta(references: tuple[int, int | None]) -> tantivy.Document:
        doc = tantivy.Document(identity="meta", source="meta")
        doc.add_bytes("payload", orjson.dumps(references))
        return doc

    async def rebuild(self, index: tantivy.Index, writer: tantivy.IndexWriter) -> None:
        """Replace every document in one commit, projecting the database in bounded batches."""

        def add(documents: Iterable[tantivy.Document]) -> None:
            for document in documents:
                writer.add_document(document)

        async def page[T](statement: Select[T]) -> list[T]:
            async with self.sessions() as session:
                return list((await session.scalars(statement.limit(BATCH))).all())

        await _native(writer.delete_all_documents)
        after, reference_count = 0, 0
        while reference := await page(
            select(ReferenceWord).where(ReferenceWord.id > after).order_by(ReferenceWord.id)
        ):
            after = reference[-1].id
            reference_count += len(reference)
            await _native(partial(add, self.documents(([], [], [], [], set()), reference)))
        writer.add_document(self.meta((reference_count, after if reference_count else None)))

        def add_words(projection: SearchProjection) -> None:
            for identifier in projection[4]:
                writer.delete_documents_by_term("identity", f"reference:{identifier}")
            add(self.documents(projection, []))

        done = rows.Word.generation_state == GenerationState.DONE
        after = 0
        while ids := await page(
            select(rows.Word.id).where(done, rows.Word.id > after).order_by(rows.Word.id)
        ):
            after = ids[-1]
            projection = await self.projection(ids[0], after)
            await _native(partial(add_words, projection))
        await _native(writer.commit)
        await _native(index.reload)

    async def start(self) -> None:
        async with self.lock:
            if self.snapshot is not None:
                return
            index = await asyncio.to_thread(self.open)
            fingerprint = await self.fingerprint()
            stored = await _native(lambda: self.stored_fingerprint(index))
            if stored == fingerprint:
                self.snapshot = index
                logger.info(
                    "search_index_started", rebuilt=False, documents=index.searcher().num_docs
                )
                return

            writer = await self.lease(index)
            try:
                fingerprint = await self.fingerprint()
                stored = await _native(lambda: self.stored_fingerprint(index))
                rebuilt = stored != fingerprint
                if rebuilt:
                    await self.rebuild(index, writer)
            finally:
                await _native(writer.wait_merging_threads)
                del writer
            self.snapshot = index
            logger.info(
                "search_index_started", rebuilt=rebuilt, documents=index.searcher().num_docs
            )

    async def update(self, word_id: int) -> None:
        started = perf_counter()
        async with self.lock:
            self.ready()
            index = cast(tantivy.Index, self.snapshot)
            projection = await self.projection(word_id, word_id)
            writer = await self.lease(index)

            def publish(writer: tantivy.IndexWriter) -> None:
                try:
                    writer.delete_documents_by_term("identity", f"word:{word_id}")
                    for identifier in projection[4]:
                        writer.delete_documents_by_term("identity", f"reference:{identifier}")
                    for document in self.documents(projection, []):
                        writer.add_document(document)
                    writer.commit()
                finally:
                    writer.wait_merging_threads()
                index.reload()

            try:
                await _native(partial(publish, writer))
            finally:
                del writer
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
        snapshot: tantivy.Index | None,
        query: str,
        include_reference: bool,
        limit: int,
    ) -> list[WordHit | ReferenceHit]:
        assert snapshot is not None
        searcher = snapshot.searcher()
        schema, key = snapshot.schema, answer_key(query)
        ranked: dict[str, tuple[tuple[int, int, int, str, int], WordHit | ReferenceHit]] = {}

        def candidate(payload: list[Any], kind: MatchKind) -> None:
            identity = payload[0]
            if identity in ranked:
                return
            _, label, entry_value, matched_surface, rank, _forms = payload
            generated = identity.startswith("word:")
            identifier = int(identity.partition(":")[2])
            entry_type = EntryType(entry_value)
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
                MATCH_KIND_ORDER[kind],
                int(not generated),
                rank,
                answer_key(label),
                identifier,
            )
            ranked[identity] = (order, hit)

        literal = "".join("\\" + char if char in r"\.^$|?*+(){}[]" else char for char in key)
        for kind in MatchKind:
            if kind is MatchKind.PREFIX:
                heads = tantivy.Query.boolean_query(
                    [
                        (tantivy.Occur.Should, tantivy.Query.term_query(schema, "head", head))
                        for head in {surface_head_key(key), "\0"}
                    ]
                )
                fetched, size = 0, limit
                generated = sum(order[1] == 0 for order, _hit in ranked.values())
                while generated < limit:
                    hits = searcher.search(
                        heads,
                        limit=size,
                        count=False,
                        order_by_field="order",
                        order=tantivy.Order.Asc,
                    ).hits
                    for _score, address in hits[fetched:]:
                        payload = _payload(searcher.doc(address))
                        if payload[0] not in ranked and matches_pattern(
                            payload[3], query, forms=payload[5]
                        ):
                            candidate(payload, MatchKind.EXACT)
                            generated += 1
                        if generated >= limit:
                            break
                    if len(hits) < size:
                        break
                    fetched, size = size, size * 2
            if kind is not MatchKind.EXACT and len(ranked) >= limit:
                break
            if kind is MatchKind.EXACT:
                branch = tantivy.Query.term_query(schema, "surface", key)
            elif kind is MatchKind.PREFIX:
                branch = tantivy.Query.regex_query(schema, "surface", literal + ".*")
            elif kind is MatchKind.SUBSTRING:
                branch = (
                    tantivy.Query.boolean_query(
                        [
                            (
                                tantivy.Occur.Must,
                                tantivy.Query.term_query(schema, "trigram", trigram),
                            )
                            for trigram in sorted(_trigrams(key))
                        ]
                    )
                    if len(key) >= 3
                    else tantivy.Query.regex_query(schema, "surface", ".*" + literal + ".*")
                )
            else:
                if len(key) < 3:
                    break
                branch = tantivy.Query.fuzzy_term_query(
                    schema, "surface", key, distance=1 if len(key) < 6 else 2
                )
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
                hits = searcher.search(
                    combined,
                    limit=size,
                    count=False,
                    order_by_field="order",
                    order=tantivy.Order.Asc,
                ).hits
                for _score, address in hits[fetched:]:
                    payload = _payload(searcher.doc(address))
                    if kind is MatchKind.SUBSTRING and key not in answer_key(payload[3]):
                        continue
                    if payload[0] not in seen:
                        seen.add(payload[0])
                        candidate(payload, kind)
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
