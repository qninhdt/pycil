"""Async engine + FastAPI session dependency for the pycil database."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pycil.platform.settings import settings

engine = create_async_engine(settings.db_url, echo=False, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


def session_scope() -> AsyncSession:
    """A short-lived session for work outside a request dependency.

    Settlement runs from a stream's cleanup, where no request-scoped session is
    available and where holding one across provider streaming would exhaust the
    pool. Each caller opens, uses and closes this immediately.
    """
    return async_session_factory()
