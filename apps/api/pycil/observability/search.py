"""Measurements around the existing Tantivy lifecycle."""

import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from time import perf_counter
from weakref import WeakSet

import tantivy
from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.vocabulary.config import SearchPolicy, SearchRuntime
from pycil.vocabulary.errors import InvalidResourceError
from pycil.vocabulary.revisions import ContentRevision
from pycil.vocabulary.schemas import SearchResult
from pycil.vocabulary.search import SearchIndex

_indexes = WeakSet["ObservedSearchIndex"]()


def _pending_ages(_options: CallbackOptions) -> Generator[Observation]:
    now = perf_counter()
    for index in tuple(_indexes):
        if index.is_owner and index.pending_observed:
            yield Observation(
                index.pending_age(now),
                {"index": index.name},
            )


_pending_age = metrics.get_meter("pycil.search").create_observable_gauge(
    "pycil.search.pending_age",
    callbacks=[_pending_ages],
    unit="s",
    description="Age of the first pending revision at the latest successful owner poll",
)

_duration = metrics.get_meter("pycil.search").create_histogram(
    "pycil.search.duration",
    unit="s",
    explicit_bucket_boundaries_advisory=(
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2.5,
        5,
        10,
        30,
        60,
    ),
)


class ObservedSearchIndex(SearchIndex):
    _pending_observed: bool
    _observed_pending_since: float | None

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        path: str | None = None,
        *,
        name: str,
        policy: SearchRuntime,
        query_policy: SearchPolicy,
    ) -> None:
        super().__init__(sessions, path, policy=policy, query_policy=query_policy)
        self.name = name
        self._pending_observed = False
        self._observed_pending_since = None
        _indexes.add(self)

    @property
    def pending_observed(self) -> bool:
        return self._pending_observed

    def pending_age(self, now: float) -> float:
        if self._observed_pending_since is None:
            return 0.0
        return max(0.0, now - self._observed_pending_since)

    @contextmanager
    def _measure(self, operation: str) -> Generator[dict[str, str]]:
        started = perf_counter()
        attributes = {"index": self.name, "operation": operation, "outcome": "succeeded"}
        try:
            yield attributes
        except asyncio.CancelledError:
            attributes["outcome"] = "cancelled"
            raise
        except InvalidResourceError:
            attributes["outcome"] = "rejected"
            raise
        except Exception:
            attributes["outcome"] = "failed"
            raise
        finally:
            _duration.record(perf_counter() - started, attributes)

    async def search(
        self, query: str, include_reference: bool = False, *, limit: int | None = None
    ) -> SearchResult:
        with self._measure("query"):
            return await super().search(query, include_reference, limit=limit)

    async def synchronize(self, writer: tantivy.IndexWriter) -> bool:
        with self._measure("synchronize") as attributes:
            changed = await super().synchronize(writer)
            if not changed:
                attributes["outcome"] = "idle"
            return changed

    async def pending_revisions(self, session: AsyncSession, cursor: int) -> list[ContentRevision]:
        changes = await super().pending_revisions(session, cursor)
        self._observed_pending_since = (
            perf_counter() - max(0, (datetime.now(UTC) - changes[0].created_at).total_seconds())
            if changes
            else None
        )
        self._pending_observed = True
        return changes

    async def rebuild(self, index: tantivy.Index, writer: tantivy.IndexWriter) -> None:
        with self._measure("rebuild"):
            await super().rebuild(index, writer)

    async def wait_for_revision(self, revision: int) -> None:
        with self._measure("publication_wait"):
            await super().wait_for_revision(revision)

    async def close(self) -> None:
        try:
            await super().close()
        finally:
            self._pending_observed = False
