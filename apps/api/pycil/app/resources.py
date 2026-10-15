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
from pycil.app.settings import ApiSettings, ProcessSettings, WorkerSettings
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.infrastructure.database import connect, verify_schema
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.infrastructure.llm import DecisionLLM, StructuredLLM
from pycil.infrastructure.observability import ObservedAsyncClient, get_logger, telemetry
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
            async with asyncio.timeout(config.runtime.lifecycle.cleanup_timeout_seconds):
                await stack.aclose()
            logger.info("resources_closed", duration_ms=round((perf_counter() - started) * 1000, 2))
        except Exception as exc:
            logger.error("resources_cleanup_failed", error_type=type(exc).__name__)
            raise RuntimeError("Runtime resource cleanup failed") from None


async def _open_process_resources(
    stack: AsyncExitStack, config: AppConfig, settings: ProcessSettings
) -> ProcessResources:
    await stack.enter_async_context(telemetry(settings, config.runtime.telemetry))
    engine, sessions = connect(
        settings.db_url.get_secret_value(), **config.runtime.database.application_pool.model_dump()
    )
    stack.push_async_callback(engine.dispose)
    redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        settings.redis_url.get_secret_value(),
        max_connections=config.runtime.redis.max_connections,
        socket_connect_timeout=config.runtime.redis.connect_timeout_seconds,
        socket_timeout=config.runtime.redis.operation_timeout_seconds,
    )
    stack.push_async_callback(redis.aclose)
    await verify_schema(engine)
    await redis.ping()  # pyright: ignore[reportUnknownMemberType]
    http = await stack.enter_async_context(
        ObservedAsyncClient(timeout=config.runtime.http.client_timeout_seconds)
    )
    policy = config.runtime.caches
    word_store = InMemoryStore[int, CachedWord](policy.words.max_entries, policy.words.ttl_seconds)
    sense_store = InMemoryStore[int, Sense](policy.senses.max_entries, policy.senses.ttl_seconds)
    artifact_store = InMemoryStore[int, Artifact](
        policy.artifacts.max_entries, policy.artifacts.ttl_seconds
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
                config.runtime.providers.vocabulary,
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
            policy = config.runtime.caches.user_id
            user_id_store = InMemoryStore[str, UUID](policy.max_entries, policy.ttl_seconds)
            stack.callback(user_id_store.clear)
            shared.sessions.configure(info={"user_id_store": user_id_store})
            pool = await stack.enter_async_context(
                checkpoint_pool(
                    settings.db_url.get_secret_value(),
                    **config.runtime.database.checkpoint_pool.model_dump(),
                )
            )
            decision_llm = DecisionLLM(
                config.runtime.providers.vocabulary,
                api_key=settings.decision_api_key.get_secret_value(),
                endpoint=settings.decision_base_url,
                http_client=shared.http,
            )
            search = SearchIndex(
                shared.sessions,
                settings.search_index_path,
                policy=config.runtime.search,
                query_policy=config.product.vocabulary.search,
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
