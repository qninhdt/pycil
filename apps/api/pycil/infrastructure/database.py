"""One application metadata and fresh sessions for concurrent operations."""

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from time import perf_counter
from typing import Any

from sqlalchemy import (
    Enum,
    FromClause,
    MetaData,
    ScalarSelect,
    cast,
    event,
    func,
    literal,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection, ExceptionContext, ExecutionContext
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool, PoolProxiedConnection
from sqlalchemy.sql.expression import ColumnExpressionArgument

from pycil.infrastructure.observability import (
    get_logger,
    observe_pool_acquisition,
    record_database_duration,
)

logger = get_logger(__name__)


class ApplicationPool(AsyncAdaptedQueuePool):
    def connect(self) -> PoolProxiedConnection:
        with observe_pool_acquisition("application"):
            return super().connect()


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def enum_column[E: StrEnum](enum: type[E]) -> Enum:
    def _values(members: Iterable[E]) -> list[str]:
        return [member.value for member in members]

    return Enum(
        enum,
        native_enum=False,
        values_callable=_values,
        create_constraint=True,
        validate_strings=True,
        name=enum.__name__.lower(),
    )


def connect(
    url: str,
    *,
    size: int = 5,
    max_overflow: int = 0,
    timeout_seconds: float = 2,
    connect_timeout_seconds: float = 60,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Pycil requires an explicit PostgreSQL async URL")
    engine = create_async_engine(
        url,
        poolclass=ApplicationPool,
        pool_pre_ping=True,
        pool_size=size,
        max_overflow=max_overflow,
        pool_timeout=timeout_seconds,
        hide_parameters=True,
        connect_args={
            "timeout": connect_timeout_seconds,
            "server_settings": {"search_path": "public"},
        },
    )

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def query_started(
        _connection: Connection,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        if context is not None:
            context._pycil_query_started = perf_counter()  # pyright: ignore[reportAttributeAccessIssue]

    def query_finished(
        context: ExecutionContext | None,
        error: BaseException | None = None,
    ) -> None:
        if context is not None:
            started: Any = getattr(context, "_pycil_query_started", None)
            if isinstance(started, float):
                try:
                    delattr(context, "_pycil_query_started")
                except AttributeError:
                    pass
                record_database_duration("query", "application", started, error)

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def query_succeeded(
        _connection: Connection,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        query_finished(context)

    @event.listens_for(engine.sync_engine, "handle_error")
    def query_failed(context: ExceptionContext) -> None:
        query_finished(context.execution_context, context.original_exception)

    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def transaction_lock(session: AsyncSession, key: str) -> None:
    """Serialize one business resource; release automatically with its transaction."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
    )


def json_collection(
    source: FromClause,
    fields: Mapping[str, ColumnExpressionArgument[object]],
    *conditions: ColumnExpressionArgument[bool],
    order_by: Sequence[ColumnExpressionArgument[object]] = (),
    correlate: Sequence[FromClause] = (),
) -> ScalarSelect[object]:
    """Ordered nested rows in one PostgreSQL statement snapshot."""
    pairs: list[object] = [
        part for name, value in fields.items() for part in (literal(name), value)
    ]
    items = (
        select(func.jsonb_build_object(*pairs).label("item"))
        .select_from(source)
        .where(*conditions)
        .order_by(*order_by)
        .correlate(*correlate)
        .subquery()
    )
    return select(
        func.coalesce(func.jsonb_agg(items.c.item), cast(literal("[]"), JSONB))
    ).scalar_subquery()


def register_models():
    from pycil.account import models as account
    from pycil.assistant import models as assistant
    from pycil.infrastructure import content_revisions
    from pycil.library import models as library
    from pycil.study import models as study
    from pycil.themes import models as themes
    from pycil.vocabulary import models as vocabulary
    from pycil.vocabulary.references import models as reference

    return account, assistant, library, study, themes, vocabulary, reference, content_revisions


async def verify_schema(engine: AsyncEngine, *, require_reference: bool = True) -> None:
    """Read-only gate; missing or obsolete tables are never repaired on startup."""
    from alembic.script import ScriptDirectory
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from pycil.app.migrate import migration_config

    register_models()
    head = ScriptDirectory.from_config(migration_config("postgresql+asyncpg://")).get_current_head()
    try:
        async with engine.connect() as connection:
            versions = (
                (await connection.execute(text("SELECT version_num FROM public.alembic_version")))
                .scalars()
                .all()
            )
            native = (
                (
                    await connection.execute(
                        text("SELECT v FROM public.checkpoint_migrations ORDER BY v")
                    )
                )
                .scalars()
                .all()
            )
            if versions != [head] or native != list(range(len(AsyncPostgresSaver.MIGRATIONS))):
                raise RuntimeError("schema_version_mismatch; run the explicit setup command")
            required = set(Base.metadata.tables) | {
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
            }
            existing = set(
                (
                    await connection.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                    )
                ).scalars()
            )
            if not required <= existing:
                raise RuntimeError("schema_tables_missing; run the explicit setup command")
            if require_reference and not await connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM reference_words)")
            ):
                raise RuntimeError("reference_dataset_missing; import reference JSONL explicitly")
        logger.info("schema_verification_passed")
    except Exception as error:
        logger.error("schema_verification_failed", error_type=type(error).__name__)
        raise
