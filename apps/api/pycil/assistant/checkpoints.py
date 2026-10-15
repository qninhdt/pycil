from collections.abc import AsyncGenerator, Generator, Iterable
from contextlib import asynccontextmanager, contextmanager
from typing import Self, cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from opentelemetry import trace
from psycopg import AsyncConnection, AsyncCursor
from psycopg.abc import Params, Query, QueryNoTemplate
from psycopg.pq import PipelineStatus
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

from pycil.infrastructure.observability import observe_pool_acquisition

_query_tracer = trace.get_tracer("pycil.checkpoints")
_sql_operations = frozenset("SELECT INSERT UPDATE DELETE WITH SET SHOW".split())


class CheckpointCursor[Row](AsyncCursor[Row]):
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
                "pycil.db.pool": "checkpoint",
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


class CheckpointPool(AsyncConnectionPool[AsyncConnection[DictRow]]):
    async def getconn(self, timeout: float | None = None) -> AsyncConnection[DictRow]:
        with observe_pool_acquisition("checkpoint"):
            return await super().getconn(timeout=timeout)


def checkpoint_dsn(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg":
        raise ValueError("Checkpoint storage requires the application PostgreSQL URL")
    return str(parsed.set(drivername="postgresql").render_as_string(hide_password=False))


@asynccontextmanager
async def checkpoint_pool(
    url: str,
    *,
    min_size: int = 1,
    max_size: int = 3,
    timeout_seconds: float = 30,
    startup_timeout_seconds: float = 30,
) -> AsyncGenerator[AsyncConnectionPool[AsyncConnection[DictRow]]]:
    async with CheckpointPool(
        checkpoint_dsn(url),
        min_size=min_size,
        max_size=max_size,
        timeout=timeout_seconds,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "cursor_factory": CheckpointCursor,
            "options": "-c search_path=public",
        },
    ) as pool:
        await pool.wait(timeout=startup_timeout_seconds)
        yield pool


@asynccontextmanager
async def checkpoint_connection(
    url: str,
) -> AsyncGenerator[AsyncConnection[DictRow]]:
    connection = await AsyncConnection[DictRow].connect(
        checkpoint_dsn(url),
        autocommit=True,
        connect_timeout=5,
        prepare_threshold=0,
        row_factory=dict_row,
        options="-c search_path=public",
    )
    async with connection:
        yield connection


async def setup_checkpoints(url: str) -> None:
    # Native setup uses autocommit (including CREATE INDEX CONCURRENTLY).
    # No DDL or local substitute checkpoint tables appear in Pycil's Alembic history.
    async with checkpoint_connection(url) as connection:
        await connection.execute("SET lock_timeout = '5s'")
        await connection.execute("SET statement_timeout = '120s'")
        await AsyncPostgresSaver(connection).setup()
