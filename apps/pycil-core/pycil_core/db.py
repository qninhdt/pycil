from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pycil_core.config import get_settings

_settings = get_settings()

# Async engine for runtime app code.
engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an AsyncSession, commits/rolls back automatically."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
