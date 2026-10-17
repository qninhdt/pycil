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
from taskiq import AsyncBroker

from pycil.app.config import AppConfig
from pycil.app.http import Problem
from pycil.app.settings import ApiSettings
from pycil.infrastructure.clerk import Identity
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.infrastructure.llm import DecisionLLM
from pycil.observability import get_logger
from pycil.study.artifacts.schemas import Artifact
from pycil.vocabulary.schemas import CachedWord, Sense
from pycil.vocabulary.search import SearchIndex

logger = get_logger(__name__)


class AppState(Protocol):
    config: AppConfig
    broker: AsyncBroker
    deployment: ApiSettings
    identity: Identity
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    user_id_store: InMemoryStore[str, UUID]
    http: httpx.AsyncClient
    decision_llm: DecisionLLM
    search: SearchIndex
    word_store: InMemoryStore[int, CachedWord]
    sense_store: InMemoryStore[int, Sense]
    artifact_store: InMemoryStore[int, Artifact]
    checkpoint_pool: AsyncConnectionPool[AsyncConnection[DictRow]]


def resources(request: Request) -> AppState:
    return cast(AppState, request.app.state)


Runtime = Annotated[AppState, Depends(resources)]


async def session(runtime: Runtime) -> AsyncGenerator[AsyncSession]:
    async with runtime.sessions() as connection:
        try:
            yield connection
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "57014":
                logger.warning("database_query_timeout", sqlstate="57014")
                raise Problem(503, "query_timeout") from None
            raise


def configuration(runtime: Runtime) -> AppConfig:
    return runtime.config


Session = Annotated[AsyncSession, Depends(session)]
Config = Annotated[AppConfig, Depends(configuration)]
