import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from uuid import UUID

import httpx
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pycil.app.config import AppConfig
from pycil.app.settings import Deployment
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.infrastructure.cache import MemoryCache
from pycil.infrastructure.database import connect, verify_schema
from pycil.infrastructure.llm import DecisionLLM, StructuredLLM
from pycil.infrastructure.observability import get_logger
from pycil.study.artifacts.schemas import Artifact
from pycil.vocabulary.generation.jobs import Generations
from pycil.vocabulary.schemas import CachedWord, Sense
from pycil.vocabulary.search import SearchIndex

logger = get_logger(__name__)


@dataclass
class RuntimeState:
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


@asynccontextmanager
async def process_resources(
    config: AppConfig, deployment: Deployment
) -> AsyncGenerator[RuntimeState]:
    """One set of owned, explicitly closed native resources per API process."""
    stack = AsyncExitStack()
    started = perf_counter()
    try:
        try:
            url = deployment.db_url.get_secret_value()
            engine, sessions = connect(url, **config.runtime.database.application_pool.model_dump())
            stack.push_async_callback(engine.dispose)
            redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
                deployment.redis_url.get_secret_value(),
                socket_connect_timeout=config.runtime.redis.connect_timeout_seconds,
                socket_timeout=config.runtime.redis.operation_timeout_seconds,
            )
            stack.push_async_callback(redis.aclose)
            await verify_schema(engine)
            await redis.ping()  # pyright: ignore[reportUnknownMemberType]
            namespace = (
                "pycil:cache:v3:"
                + sha256((url + "\0" + deployment.clerk_issuer).encode()).hexdigest()
            )
            cache_policy = config.runtime.caches
            user_id_cache = MemoryCache[str, UUID](
                cache_policy.user_id.max_entries, cache_policy.user_id.ttl_seconds
            )
            stack.callback(user_id_cache.clear)
            sessions.configure(info={"user_id_cache": user_id_cache})
            http = await stack.enter_async_context(
                httpx.AsyncClient(timeout=config.runtime.http.client_timeout_seconds)
            )
            pool = await stack.enter_async_context(
                checkpoint_pool(url, **config.runtime.database.checkpoint_pool.model_dump())
            )
            policy = config.runtime.providers.vocabulary
            structured_llm = StructuredLLM(
                policy,
                api_key=deployment.llm_api_key.get_secret_value(),
                base_url=deployment.llm_base_url,
                http_client=http,
            )
            decision_llm = DecisionLLM(
                policy,
                api_key=deployment.decision_api_key.get_secret_value(),
                endpoint=deployment.decision_base_url,
                http_client=http,
            )
            word_cache = MemoryCache[int, CachedWord](
                cache_policy.words.max_entries, cache_policy.words.ttl_seconds
            )
            sense_cache = MemoryCache[int, Sense](
                cache_policy.senses.max_entries, cache_policy.senses.ttl_seconds
            )
            artifact_cache = MemoryCache[int, Artifact](
                cache_policy.artifacts.max_entries, cache_policy.artifacts.ttl_seconds
            )
            stack.callback(word_cache.clear)
            stack.callback(sense_cache.clear)
            stack.callback(artifact_cache.clear)
            search = SearchIndex(
                sessions,
                deployment.search_index_path,
                policy=config.runtime.search,
                query_policy=config.product.vocabulary.search,
            )
            stack.push_async_callback(search.close)
            await search.start()
            generations = Generations(
                sessions,
                search,
                structured_llm,
                word_cache,
                config,
                sense_cache=sense_cache,
                redis=redis,
                prefix=namespace + ":word-tasks",
            )
            stack.push_async_callback(generations.close)
            logger.info(
                "resources_initialized", duration_ms=round((perf_counter() - started) * 1000, 2)
            )
        except Exception as exc:
            logger.error("resources_initialization_failed", error_type=type(exc).__name__)
            raise RuntimeError(
                "Runtime initialization failed; verify deployment, reference dataset, "
                "PostgreSQL/Redis and explicit migration gate"
            ) from None
        yield RuntimeState(
            engine=engine,
            sessions=sessions,
            redis=redis,
            user_id_cache=user_id_cache,
            http=http,
            structured_llm=structured_llm,
            decision_llm=decision_llm,
            search=search,
            word_cache=word_cache,
            sense_cache=sense_cache,
            artifact_cache=artifact_cache,
            generations=generations,
            checkpoint_pool=pool,
        )
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
