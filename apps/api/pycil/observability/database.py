"""Observe native SQLAlchemy and psycopg operations without capturing SQL."""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Self, cast

from opentelemetry import trace
from psycopg import AsyncConnection, AsyncCursor
from psycopg.abc import Params, Query, QueryNoTemplate
from psycopg.pq import PipelineStatus
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool
from sqlalchemy import event
from sqlalchemy.engine import Connection, ExceptionContext, ExecutionContext
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool, PoolProxiedConnection

from pycil.infrastructure.database import connect
from pycil.observability import observe_pool_acquisition, record_database_duration

_query_tracer = trace.get_tracer("pycil.database")
_sql_operations = frozenset("SELECT INSERT UPDATE DELETE WITH SET SHOW".split())


class ObservedSQLAlchemyPool(AsyncAdaptedQueuePool):
    def connect(self) -> PoolProxiedConnection:
        with observe_pool_acquisition(self.logging_name or "default"):
            return super().connect()


def observed_connect(
    url: str, *, name: str, **options: Any
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine, sessions = connect(url, poolclass=ObservedSQLAlchemyPool, name=name, **options)
    observe_engine(engine, name)
    return engine, sessions


def observe_engine(engine: AsyncEngine, name: str) -> None:
    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def query_started(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        if context is not None:
            context._pycil_query_started = perf_counter()  # pyright: ignore[reportAttributeAccessIssue]
            operation = statement.split(None, 1)[0].upper() if statement.strip() else "SQL"
            if operation not in _sql_operations:
                operation = "SQL"
            # Contrib 0.66b0 excludes SQLAlchemy 2.1; reuse these hooks without SQL capture.
            context._pycil_query_span = _query_tracer.start_span(  # pyright: ignore[reportAttributeAccessIssue]
                operation,
                kind=trace.SpanKind.CLIENT,
                attributes={"db.system.name": "postgresql", "db.operation.name": operation},
            )

    def query_finished(
        context: ExecutionContext | None,
        error: BaseException | None = None,
    ) -> None:
        if context is not None:
            started: object = getattr(context, "_pycil_query_started", None)
            if isinstance(started, float):
                try:
                    delattr(context, "_pycil_query_started")
                except AttributeError:
                    pass
                record_database_duration("query", name, started, error)
            span_val: object = getattr(context, "_pycil_query_span", None)
            if isinstance(span_val, trace.Span):
                try:
                    delattr(context, "_pycil_query_span")
                except AttributeError:
                    pass
                if error is not None:
                    span_val.set_attribute("error.type", type(error).__name__)
                    span_val.set_status(trace.Status(trace.StatusCode.ERROR))
                span_val.end()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def query_succeeded(
        _connection: Connection,
        _cursor: object,
        _statement: str,
        _parameters: object,
        context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        query_finished(context)

    @event.listens_for(engine.sync_engine, "handle_error")
    def query_failed(context: ExceptionContext) -> None:
        query_finished(context.execution_context, context.original_exception)


class ObservedPsycopgCursor[Row](AsyncCursor[Row]):
    def __init__(self, *args: Any, observation_name: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.observation_name = observation_name

    @contextmanager
    def _observe(self, query: Query) -> Generator[None]:
        operation = (
            query.split(None, 1)[0].upper() if isinstance(query, str) and query.strip() else "SQL"
        )
        if operation not in _sql_operations:
            operation = "SQL"
        # Pipeline execute may only enqueue; later sync errors belong to the enclosing operation.
        mode = (
            "direct" if self.connection.info.pipeline_status == PipelineStatus.OFF else "pipeline"
        )
        with _query_tracer.start_as_current_span(
            operation,
            kind=trace.SpanKind.CLIENT,
            attributes={
                "db.system.name": "postgresql",
                "db.operation.name": operation,
                "pycil.db.pool": self.observation_name,
                "pycil.db.execution.mode": mode,
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield
            except BaseException as error:
                span.set_attribute("error.type", type(error).__name__)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                raise

    async def execute(
        self,
        query: Query,
        params: Params | None = None,
        *,
        prepare: bool | None = None,
        binary: bool | None = None,
    ) -> Self:
        with self._observe(query):
            return await super().execute(
                cast(QueryNoTemplate, query), params, prepare=prepare, binary=binary
            )

    async def executemany(
        self, query: Query, params_seq: Iterable[Params], *, returning: bool = False
    ) -> None:
        with self._observe(query):
            return await super().executemany(query, params_seq, returning=returning)


class ObservedPsycopgPool(AsyncConnectionPool[AsyncConnection[DictRow]]):
    async def getconn(self, timeout: float | None = None) -> AsyncConnection[DictRow]:
        with observe_pool_acquisition(self.name):
            return await super().getconn(timeout=timeout)
