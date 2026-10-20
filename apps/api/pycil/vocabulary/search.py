"""A Tantivy index shared on disk by API processes, with serialized incremental publication."""

import asyncio
import fcntl
import random
import re
from collections import defaultdict
from collections.abc import Generator, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

import orjson
import tantivy
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.observability import get_logger
from pycil.utils.concurrency import shielded_to_thread
from pycil.utils.strings import ngrams
from pycil.vocabulary import models as rows
from pycil.vocabulary.config import SearchPolicy, SearchRuntime
from pycil.vocabulary.enums import EntryType, GenerationState, HitKind, MatchKind
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.patterns import matches_pattern, surface_head_key
from pycil.vocabulary.references.models import ReferenceWord
from pycil.vocabulary.references.reference import encode_reference_id
from pycil.vocabulary.revisions import ContentRevision, replay_many
from pycil.vocabulary.revisions import head as revision_head
from pycil.vocabulary.schemas import ReferenceHit, SearchResult, WordHit
from pycil.vocabulary.text import SLOT, answer_key
from pycil.vocabulary.types import SearchPayload

logger = get_logger(__name__)
# Bump whenever fields or document contents change; a new directory forces a rebuild.
SCHEMA_VERSION = 4
MATCH_KIND_ORDER = {
    MatchKind.EXACT: 0,
    MatchKind.PREFIX: 1,
    MatchKind.SUBSTRING: 2,
    MatchKind.FUZZY: 3,
}


def _schema() -> tantivy.Schema:
    """Index only what queries match or sort on; hit display data lives in one stored payload."""
    builder = tantivy.SchemaBuilder()
    for name in ("identity", "source", "surface", "head", "order", "trigram", "pattern_anchor"):
        builder.add_text_field(
            name, fast=name == "order", tokenizer_name="raw", index_option="basic"
        )
    builder.add_bytes_field("payload", stored=True, indexed=False)
    builder.add_unsigned_field("identifier", fast=True)
    return builder.build()


def _trigrams(value: str) -> set[str]:
    return ngrams(value, 3)


def _payload(doc: tantivy.Document) -> SearchPayload:
    """`[identity, label, entry_type, matched_surface, surface_rank, forms | None]`."""
    return cast(SearchPayload, tuple(orjson.loads(cast(bytes, doc["payload"][0]))))


_native = shielded_to_thread


type SearchProjection = tuple[
    list[tuple[int, str, EntryType | None]],
    list[tuple[int, str]],
    list[tuple[int, int, str]],
    list[tuple[int, int, str, str | None]],
    set[int],
]


class SearchIndex:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        path: str | None = None,
        *,
        policy: SearchRuntime,
        query_policy: SearchPolicy,
    ) -> None:
        self.sessions = sessions
        self.path = path
        self.snapshot: tantivy.Index | None = None
        self.lock = asyncio.Lock()
        self.policy = policy
        self.query_policy = query_policy
        self.task: asyncio.Task[None] | None = None
        self.failure: Exception | None = None
        self.is_owner = False
        self.initialized = False
        self.last_success = perf_counter()
        self.pending_since: float | None = None
        self.last_observed_cursor = 0

    async def projection(
        self,
        first: int,
        last: int,
        *,
        session: AsyncSession | None = None,
        identifiers: Sequence[int] | None = None,
    ) -> SearchProjection:
        if session is None:
            async with self.sessions() as owned:
                async with owned.begin():
                    await owned.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                    return await self.projection(
                        first, last, session=owned, identifiers=identifiers
                    )
        words: list[tuple[int, str, EntryType | None]] = [
            (row[0], row[1], row[2])
            for row in (
                await session.execute(
                    select(rows.Word.id, rows.Word.lemma, rows.Word.entry_type).where(
                        rows.Word.generation_state == GenerationState.DONE,
                        (
                            rows.Word.id.between(first, last)
                            if identifiers is None
                            else rows.Word.id.in_(identifiers)
                        ),
                    )
                )
            ).all()
        ]
        # Freeze membership: another process may finish a pending word between queries.
        word_ids = [identifier for identifier, _lemma, _kind in words]
        if not word_ids:
            return [], [], [], [], set()
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
            licensed: list[str] = []
            for form in sense_forms[sense_id]:
                form_head, _, form_tail = answer_key(form).partition(" ")
                if not form_tail or form_tail == tail:
                    licensed.append(form_head)
            doc = document(identity, 3, pattern, {first: licensed})
            # Fixed literals outside the inflected head must occur in every matching surface.
            prefix, *suffixes = SLOT.split(pattern)
            literals = [
                answer_key(part).replace("ı", "i")
                for part in [prefix.partition(" ")[2], *suffixes]
                if part.strip()
            ]
            anchor = max(literals, key=len, default="")
            doc.add_text("pattern_anchor", anchor[:3] or "\0")
            for candidate_head in {
                head,
                *(surface_head_key(form) for form in sense_forms[sense_id]),
            }:
                doc.add_text("head", candidate_head or "\0")
            yield doc

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

    def cursor(self) -> int | None:
        index = self.snapshot
        if index is None:
            return None
        index.reload()
        searcher = index.searcher()
        hits = searcher.search(tantivy.Query.term_query(index.schema, "identity", "meta"), 1).hits
        if not hits:
            return None
        value = orjson.loads(cast(bytes, searcher.doc(hits[0][1])["payload"][0]))
        if value.get("schema") != SCHEMA_VERSION:
            raise RuntimeError("incompatible search checkpoint")
        return int(value["revision"])

    @staticmethod
    def meta(revision: int) -> tantivy.Document:
        doc = tantivy.Document(identity="meta", source="meta")
        doc.add_bytes("payload", orjson.dumps({"schema": SCHEMA_VERSION, "revision": revision}))
        return doc

    async def rebuild(self, index: tantivy.Index, writer: tantivy.IndexWriter) -> None:
        """One repeatable-read snapshot and one commit for documents plus checkpoint."""
        started = perf_counter()
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            high_water = await revision_head(session)
            await _native(writer.delete_all_documents)
            after = 0
            while reference := list(
                await session.scalars(
                    select(ReferenceWord)
                    .where(ReferenceWord.id > after)
                    .order_by(ReferenceWord.id)
                    .limit(self.policy.rebuild_batch_size)
                )
            ):
                after = reference[-1].id
                await _native(
                    lambda: self._add(writer, self.documents(([], [], [], [], set()), reference))
                )
            after = 0
            while identifiers := list(
                await session.scalars(
                    select(rows.Word.id)
                    .where(rows.Word.generation_state == GenerationState.DONE, rows.Word.id > after)
                    .order_by(rows.Word.id)
                    .limit(self.policy.rebuild_batch_size)
                )
            ):
                after = identifiers[-1]
                projection = await self.projection(identifiers[0], after, session=session)

                def add_page(projection: SearchProjection = projection) -> None:
                    for identifier in projection[4]:
                        writer.delete_documents_by_term("identity", f"reference:{identifier}")
                    self._add(writer, self.documents(projection, []))

                await _native(add_page)
            await _native(lambda: self._commit(writer, high_water))
        await _native(index.reload)
        logger.info("search_rebuilt", duration_ms=round((perf_counter() - started) * 1000, 2))

    @staticmethod
    def _add(writer: tantivy.IndexWriter, documents: Iterable[tantivy.Document]) -> None:
        for document in documents:
            writer.add_document(document)

    def _commit(self, writer: tantivy.IndexWriter, cursor: int) -> None:
        writer.delete_documents_by_term("identity", "meta")
        writer.add_document(self.meta(cursor))
        writer.commit()

    async def pending_revisions(self, session: AsyncSession, cursor: int) -> list[ContentRevision]:
        return list(
            await session.scalars(
                select(ContentRevision)
                .where(ContentRevision.id > cursor, ContentRevision.entity_type == "word")
                .order_by(ContentRevision.id)
                .limit(self.policy.revision_batch_size)
            )
        )

    async def synchronize(self, writer: tantivy.IndexWriter) -> bool:
        cursor = self.cursor()
        assert cursor is not None
        started = perf_counter()
        async with self.sessions() as session, session.begin():
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            changes = await self.pending_revisions(session, cursor)
            if not changes:
                self.last_success = perf_counter()
                logger.debug(
                    "search_poll",
                    revisions=0,
                    pending_age_seconds=0,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                return False
            high_water = await revision_head(session)
            pending_age = max(0, (datetime.now(UTC) - changes[0].created_at).total_seconds())
            word_ids = sorted({row.entity_id for row in changes if row.entity_type == "word"})
            empty_projection: SearchProjection = ([], [], [], [], set())
            projection: SearchProjection = (
                await self.projection(
                    word_ids[0], word_ids[-1], session=session, identifiers=word_ids
                )
                if word_ids
                else empty_projection
            )
            reference_ids: set[int] = set(projection[4])
            # Restore references unlinked since the last committed checkpoint.
            for previous in (await replay_many(session, word_ids, through=cursor)).values():
                if previous and "reference_links" in previous:
                    links = cast(list[dict[str, int]], previous["reference_links"])
                    reference_ids.update(link["source_id"] for link in links)
            references = list(
                await session.scalars(
                    select(ReferenceWord)
                    .where(ReferenceWord.id.in_(reference_ids))
                    .order_by(ReferenceWord.id)
                )
            )
            consumed = set(
                await session.scalars(
                    select(rows.WordReference.source_id)
                    .join(rows.Word, rows.Word.id == rows.WordReference.word_id)
                    .where(
                        rows.WordReference.source_id.in_(reference_ids),
                        rows.Word.generation_state == GenerationState.DONE,
                    )
                )
            )
            through = changes[-1].id

            def publish_batch() -> None:
                for identifier in word_ids:
                    writer.delete_documents_by_term("identity", f"word:{identifier}")
                for identifier in reference_ids:
                    writer.delete_documents_by_term("identity", f"reference:{identifier}")
                consumed_projection: SearchProjection = ([], [], [], [], consumed)
                self._add(writer, self.documents(projection, []))
                self._add(writer, self.documents(consumed_projection, references))
                self._commit(writer, through)

            await _native(publish_batch)
        await _native(cast(tantivy.Index, self.snapshot).reload)
        self.last_success = perf_counter()
        logger.info(
            "search_reconciled",
            revisions=len(changes),
            revision_lag=high_water - through,
            pending_age_seconds=round(pending_age, 3),
            words=len(word_ids),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return True

    async def _own(self) -> None:
        writer: tantivy.IndexWriter | None = None
        try:
            while True:
                try:
                    writer = await _native(
                        lambda: cast(tantivy.Index, self.snapshot).writer(
                            heap_size=self.policy.writer_heap_bytes,
                            num_threads=self.policy.writer_threads,
                        )
                    )
                    self.is_owner = True
                    logger.info("search_writer_acquired")
                    break
                except ValueError as error:
                    if "LockBusy" not in str(error):
                        raise
                    await asyncio.sleep(
                        self.policy.ownership_retry_seconds
                        + random.uniform(0, self.policy.retry_jitter_seconds)
                    )
            target: int | None = None
            while True:
                try:
                    if self.cursor() is None:
                        await self.rebuild(cast(tantivy.Index, self.snapshot), writer)
                    if target is None:
                        async with self.sessions() as session:
                            target = await revision_head(session)
                    changed = await self.synchronize(writer)
                    if (self.cursor() or 0) >= target:
                        self.initialized = True
                    if changed:
                        continue
                except DBAPIError as error:
                    await _native(writer.rollback)
                    logger.warning("search_reconciliation_retry", error_type=type(error).__name__)
                await asyncio.sleep(
                    self.policy.poll_interval_seconds
                    + random.uniform(0, self.policy.retry_jitter_seconds)
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.failure = error
            logger.error("search_owner_failed", error_type=type(error).__name__)
        finally:
            if writer is not None:
                try:
                    # Cancelled/failed work must never be committed by teardown.
                    await _native(writer.rollback)
                finally:
                    await _native(writer.wait_merging_threads)
            self.is_owner = False
            logger.info("search_writer_released")

    async def start(self) -> None:
        async with self.lock:
            if self.task is not None:
                self.ready()
                return
            self.failure = None
            self.initialized = False
            self.pending_since = None
            self.last_success = perf_counter()
            self.snapshot = await _native(self.open)
            async with self.sessions() as session:
                target = await revision_head(session)
            current = self.cursor()
            if current is not None and current > target:
                self.snapshot = None
                raise RuntimeError(
                    "search checkpoint is ahead of restored database; invalidate derived index"
                )
            self.task = asyncio.create_task(self._own(), name="search-owner")
            try:
                async with asyncio.timeout(self.policy.startup_timeout_seconds):
                    while not self.initialized:
                        if self.failure is not None:
                            raise RuntimeError("search initialization failed") from self.failure
                        current = self.cursor()
                        # Standbys use the owner's atomic initialization/catch-up commit.
                        if current is not None and current >= target and not self.is_owner:
                            self.initialized = True
                            break
                        await asyncio.sleep(0.02)
            except BaseException:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
                self.task = None
                self.snapshot = None
                raise
            logger.info("search_index_started", owner=self.is_owner)

    async def wait_for_revision(self, revision: int) -> None:
        started = perf_counter()
        try:
            async with asyncio.timeout(self.policy.publication_timeout_seconds):
                while True:
                    self.ready()
                    if (self.cursor() or 0) >= revision:
                        return
                    await asyncio.sleep(0.02)
        except TimeoutError:
            logger.warning("search_publication_timeout")
            raise RuntimeError("committed content is awaiting search publication") from None
        finally:
            logger.info(
                "search_publication_wait", duration_ms=round((perf_counter() - started) * 1000, 2)
            )

    async def update(self, word_id: int) -> None:
        """Request-side receipt only; the owner remains the sole writer."""
        async with self.sessions() as session:
            revision = await session.scalar(
                select(func.max(ContentRevision.id)).where(
                    ContentRevision.entity_type == "word", ContentRevision.entity_id == word_id
                )
            )
        if revision is None:
            raise RuntimeError("word has no content revision; baseline existing content explicitly")
        await self.wait_for_revision(revision)

    def ready(self) -> None:
        if self.snapshot is None or not self.initialized or self.failure is not None:
            raise RuntimeError("search index is unavailable")
        if (
            self.is_owner
            and perf_counter() - self.last_success > self.policy.progress_timeout_seconds
        ):
            raise RuntimeError("search reconciliation is unhealthy")

    async def health(self) -> None:
        self.ready()
        async with self.sessions() as session:
            high_water = await revision_head(session)
        current = self.cursor()
        if current is None or current > high_water:
            raise RuntimeError("search checkpoint requires invalidation")
        if current < high_water:
            if self.pending_since is None or current != self.last_observed_cursor:
                self.pending_since = perf_counter()
            if perf_counter() - self.pending_since > self.policy.progress_timeout_seconds:
                raise RuntimeError("search reconciliation has stopped progressing")
        else:
            self.pending_since = None
        self.last_observed_cursor = current

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

        def candidate(payload: SearchPayload, kind: MatchKind) -> None:
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

        literal = re.escape(key)
        for kind in MatchKind:
            if kind is MatchKind.PREFIX:
                heads = tantivy.Query.boolean_query(
                    [
                        (tantivy.Occur.Should, tantivy.Query.term_query(schema, "head", head))
                        for head in {surface_head_key(key), "\0"}
                    ]
                )
                anchors = tantivy.Query.boolean_query(
                    [
                        (
                            tantivy.Occur.Should,
                            tantivy.Query.term_query(schema, "pattern_anchor", gram),
                        )
                        for gram in set().union(
                            *(ngrams(key.replace("ı", "i"), size) for size in (1, 2, 3)), {"\0"}
                        )
                    ]
                )
                heads = tantivy.Query.boolean_query(
                    [(tantivy.Occur.Must, heads), (tantivy.Occur.Must, anchors)]
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
        self, query: str, include_reference: bool = False, *, limit: int | None = None
    ) -> SearchResult:
        limit = self.query_policy.default_limit if limit is None else limit
        if (
            not query.strip()
            or len(query) > self.query_policy.max_query_chars
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise InvalidResourceError("invalid lexical query")
        self.ready()
        values = await asyncio.to_thread(self.find, self.snapshot, query, include_reference, limit)
        return SearchResult(items=values)

    async def close(self) -> None:
        async with self.lock:
            if self.task is not None:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
                self.task = None
            self.snapshot = None
            self.initialized = False
