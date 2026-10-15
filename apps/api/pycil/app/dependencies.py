from collections.abc import AsyncGenerator
from typing import Annotated, Protocol, cast
from uuid import UUID

import httpx
from fastapi import Depends, Request
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.app.settings import Deployment
from pycil.infrastructure.cache import MemoryCache
from pycil.infrastructure.clerk import Identity
from pycil.infrastructure.llm import DecisionLLM, StructuredLLM
from pycil.infrastructure.observability import get_logger
from pycil.study.artifacts.schemas import Artifact
from pycil.vocabulary.generation.jobs import Generations
from pycil.vocabulary.schemas import CachedWord, Sense
from pycil.vocabulary.search import SearchIndex

logger = get_logger(__name__)


class AppState(Protocol):
    config: AppConfig
    deployment: Deployment
    identity: Identity
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    user_id_cache: MemoryCache[str, UUID]
    http: httpx.AsyncClient
    structured_llm: StructuredLLM
    decision_llm: DecisionLLM
    search: SearchIndex
    word_cache: MemoryCache[int, CachedWord]
    sense_cache: MemoryCache[int, Sense]
    artifact_cache: MemoryCache[int, Artifact]
    generations: Generations
    checkpoint_pool: AsyncConnectionPool[AsyncConnection[DictRow]]


async def session(request: Request) -> AsyncGenerator[AsyncSession]:
    state = cast(AppState, request.app.state)
    async with state.sessions() as connection:
        try:
            yield connection
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "57014":
                logger.warning("database_query_timeout", sqlstate="57014")
                raise Problem(503, "query_timeout") from None
            raise


def configuration(request: Request) -> AppConfig:
    state = cast(AppState, request.app.state)
    return state.config


def resources(request: Request) -> AppState:
    return cast(AppState, request.app.state)


Session = Annotated[AsyncSession, Depends(session)]
Config = Annotated[AppConfig, Depends(configuration)]
Runtime = Annotated[AppState, Depends(resources)]
