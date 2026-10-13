from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter

import httpx
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pycil.app.config import ProductConfig
from pycil.app.settings import Deployment
from pycil.assistant.checkpoints import checkpoint_pool
from pycil.infrastructure.cache import RedisCache
from pycil.infrastructure.database import connect, verify_schema
from pycil.infrastructure.llm import DecisionLLM, StructuredLLM
from pycil.infrastructure.observability import get_logger
from pycil.vocabulary.cache import ContentCache
from pycil.vocabulary.generation.jobs import Generations
from pycil.vocabulary.search import SearchIndex

logger = get_logger(__name__)


@dataclass
class RuntimeState:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    cache: RedisCache
    http: httpx.AsyncClient
    structured_llm: StructuredLLM
    decision_llm: DecisionLLM
    search: SearchIndex
    content_cache: ContentCache
    artifact_cache: ContentCache
    generations: Generations
    checkpoint_pool: AsyncConnectionPool[AsyncConnection[DictRow]]


@asynccontextmanager
async def process_resources(
    config: ProductConfig, deployment: Deployment
) -> AsyncGenerator[RuntimeState]:
    """One set of owned, explicitly closed native resources per API process."""
    stack = AsyncExitStack()
    started = perf_counter()
    try:
        try:
            url = deployment.db_url.get_secret_value()
            engine, sessions = connect(url)
            stack.push_async_callback(engine.dispose)
            redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
                deployment.redis_url.get_secret_value(),
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            stack.push_async_callback(redis.aclose)
            await verify_schema(engine)
            await redis.ping()  # pyright: ignore[reportUnknownMemberType]
            namespace = (
                "pycil:cache:v3:"
                + sha256((url + "\0" + deployment.clerk_issuer).encode()).hexdigest()
            )
            cache = RedisCache(redis, namespace)
            sessions.configure(info={"cache": cache})
            http = await stack.enter_async_context(httpx.AsyncClient())
            pool = await stack.enter_async_context(checkpoint_pool(url))
            policy = config.providers.vocabulary
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
            content_cache, artifact_cache = ContentCache(), ContentCache()
            stack.callback(content_cache.clear)
            stack.callback(artifact_cache.clear)
            search = SearchIndex(sessions)
            stack.push_async_callback(search.close)
            await search.start()
            generations = Generations(sessions, search, structured_llm, content_cache, config)
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
            cache=cache,
            http=http,
            structured_llm=structured_llm,
            decision_llm=decision_llm,
            search=search,
            content_cache=content_cache,
            artifact_cache=artifact_cache,
            generations=generations,
            checkpoint_pool=pool,
        )
    finally:
        started = perf_counter()
        try:
            # ExitStack runs every registered closer even when one closer fails.
            await stack.aclose()
            logger.info("resources_closed", duration_ms=round((perf_counter() - started) * 1000, 2))
        except Exception as exc:
            logger.error("resources_cleanup_failed", error_type=type(exc).__name__)
            raise RuntimeError("Runtime resource cleanup failed") from None
