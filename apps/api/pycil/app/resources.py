import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

import httpx
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pycil.app.config import AppConfig
from pycil.app.schema import verify_schema
from pycil.app.settings import ApiSettings, ProcessSettings, WorkerSettings
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.infrastructure.llm import DecisionLLM, StructuredLLM
from pycil.observability import get_logger, telemetry
from pycil.observability.database import observed_connect
from pycil.observability.http import ObservedAsyncClient
from pycil.observability.search import ObservedSearchIndex
from pycil.observability.stores import ObservedInMemoryStore
from pycil.study.artifacts.schemas import Artifact
from pycil.vocabulary.schemas import CachedWord, Sense
from pycil.vocabulary.search import SearchIndex

logger = get_logger(__name__)


@dataclass
class ProcessResources:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    http: httpx.AsyncClient
    word_store: InMemoryStore[int, CachedWord]
    sense_store: InMemoryStore[int, Sense]
    artifact_store: InMemoryStore[int, Artifact]


@dataclass
class WorkerResources(ProcessResources):
    structured_llm: StructuredLLM


@dataclass
class ApiResources(ProcessResources):
    user_id_store: InMemoryStore[str, UUID]
    decision_llm: DecisionLLM
    search: SearchIndex
    checkpoint_pool: AsyncConnectionPool[AsyncConnection[DictRow]]


@asynccontextmanager
async def _resource_stack(config: AppConfig) -> AsyncGenerator[AsyncExitStack]:
    stack = AsyncExitStack()
    try:
        yield stack
    finally:
        started = perf_counter()
        try:
            # ExitStack runs every registered closer even when one closer fails.
            async with asyncio.timeout(config.system.lifecycle.cleanup_timeout_seconds):
                await stack.aclose()
            logger.info("resources_closed", duration_ms=round((perf_counter() - started) * 1000, 2))
        except Exception as exc:
            logger.error("resources_cleanup_failed", error_type=type(exc).__name__)
            raise RuntimeError("Runtime resource cleanup failed") from None


async def _open_process_resources(
    stack: AsyncExitStack, config: AppConfig, settings: ProcessSettings
) -> ProcessResources:
    await stack.enter_async_context(telemetry(settings, config.system.telemetry))
    engine, sessions = observed_connect(
        settings.db_url.get_secret_value(),
        name="application",
        **config.system.database.application_pool.model_dump(),
    )
    stack.push_async_callback(engine.dispose)
    redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        settings.redis_url.get_secret_value(),
        max_connections=config.system.redis.max_connections,
        socket_connect_timeout=config.system.redis.connect_timeout_seconds,
        socket_timeout=config.system.redis.operation_timeout_seconds,
    )
    stack.push_async_callback(redis.aclose)
    await verify_schema(engine)
    await redis.ping()  # pyright: ignore[reportUnknownMemberType]
    http = await stack.enter_async_context(
        ObservedAsyncClient(timeout=config.system.http.client_timeout_seconds)
    )
    policy = config.system.caches
    word_store = ObservedInMemoryStore[int, CachedWord](
        policy.words.max_entries,
        policy.words.ttl_seconds,
        name="word",
    )
    sense_store = ObservedInMemoryStore[int, Sense](
        policy.senses.max_entries,
        policy.senses.ttl_seconds,
        name="sense",
    )
    artifact_store = ObservedInMemoryStore[int, Artifact](
        policy.artifacts.max_entries,
        policy.artifacts.ttl_seconds,
        name="artifact",
    )
    stack.callback(word_store.clear)
    stack.callback(sense_store.clear)
    stack.callback(artifact_store.clear)
    return ProcessResources(
        engine=engine,
        sessions=sessions,
        redis=redis,
        http=http,
        word_store=word_store,
        sense_store=sense_store,
        artifact_store=artifact_store,
    )


@asynccontextmanager
async def worker_resources(
    config: AppConfig, settings: WorkerSettings
) -> AsyncGenerator[WorkerResources]:
    async with _resource_stack(config) as stack:
        started = perf_counter()
        try:
            shared = await _open_process_resources(stack, config, settings)
            llm = StructuredLLM(
                config.vocabulary.provider,
                api_key=settings.llm_api_key.get_secret_value(),
                base_url=settings.llm_base_url,
                http_client=shared.http,
            )
            resources = WorkerResources(**vars(shared), structured_llm=llm)
        except Exception as exc:
            logger.error("resources_initialization_failed", error_type=type(exc).__name__)
            raise RuntimeError(
                "Runtime initialization failed; verify worker dependencies"
            ) from None
        logger.info(
            "resources_initialized", duration_ms=round((perf_counter() - started) * 1000, 2)
        )
        yield resources


@asynccontextmanager
async def api_resources(config: AppConfig, settings: ApiSettings) -> AsyncGenerator[ApiResources]:
    async with _resource_stack(config) as stack:
        started = perf_counter()
        try:
            shared = await _open_process_resources(stack, config, settings)
            policy = config.system.caches.user_id
            user_id_store = ObservedInMemoryStore[str, UUID](
                policy.max_entries,
                policy.ttl_seconds,
                name="user_id",
            )
            stack.callback(user_id_store.clear)
            pool = await stack.enter_async_context(
                checkpoint_pool(
                    settings.db_url.get_secret_value(),
                    **config.system.database.checkpoint_pool.model_dump(),
                )
            )
            decision_llm = DecisionLLM(
                config.vocabulary.provider,
                api_key=settings.decision_api_key.get_secret_value(),
                endpoint=settings.decision_base_url,
                http_client=shared.http,
            )
            search = ObservedSearchIndex(
                shared.sessions,
                settings.search_index_path,
                name="dictionary",
                policy=config.vocabulary.search_runtime,
                query_policy=config.vocabulary.search,
            )
            stack.push_async_callback(search.close)
            await search.start()
            resources = ApiResources(
                **vars(shared),
                user_id_store=user_id_store,
                decision_llm=decision_llm,
                search=search,
                checkpoint_pool=pool,
            )
        except Exception as exc:
            logger.error("resources_initialization_failed", error_type=type(exc).__name__)
            raise RuntimeError("Runtime initialization failed; verify API dependencies") from None
        logger.info(
            "resources_initialized", duration_ms=round((perf_counter() - started) * 1000, 2)
        )
        yield resources
