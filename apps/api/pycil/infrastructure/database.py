"""One application metadata and fresh sessions for concurrent operations."""

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum

from sqlalchemy import (
    Enum,
    FromClause,
    MetaData,
    ScalarSelect,
    cast,
    func,
    literal,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool
from sqlalchemy.sql.expression import ColumnExpressionArgument


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
    poolclass: type[AsyncAdaptedQueuePool] = AsyncAdaptedQueuePool,
    name: str | None = None,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("Pycil requires an explicit PostgreSQL async URL")
    engine = create_async_engine(
        url,
        poolclass=poolclass,
        pool_logging_name=name,
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

    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def lock_rows(session: AsyncSession, model: type[Base], identifiers: Iterable[int]) -> None:
    column = model.__table__.c.id
    for identifier in sorted(set(identifiers)):
        await session.execute(select(column).where(column == identifier).with_for_update())


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


