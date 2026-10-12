from contextlib import AsyncExitStack, asynccontextmanager
from hashlib import sha256
from types import SimpleNamespace
from typing import Annotated

import httpx
from fastapi import Depends, Request
from lexi_ai import DecisionConfig, Lexicon, LLMConfig
from redis.asyncio import Redis
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.assistant.checkpoints import checkpoint_pool
from pycil.cache import RedisCache
from pycil.config import Deployment, ProductConfig
from pycil.database import connect, verify_schema
from pycil.http import Problem
from pycil.vocabulary.generation import Generations


@asynccontextmanager
async def process_resources(config: ProductConfig, deployment: Deployment):
    """One set of owned, explicitly closed native resources per API process."""
    stack = AsyncExitStack()
    try:
        try:
            url = deployment.db_url.get_secret_value()
            engine, sessions = connect(url)
            stack.push_async_callback(engine.dispose)
            redis = Redis.from_url(
                deployment.redis_url.get_secret_value(),
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            stack.push_async_callback(redis.aclose)
            await verify_schema(engine)
            await redis.ping()
            namespace = (
                "pycil:cache:v3:"
                + sha256((url + "\0" + deployment.clerk_issuer).encode()).hexdigest()
            )
            cache = RedisCache(redis, namespace, config.cache)
            sessions.configure(info={"cache": cache})
            http = await stack.enter_async_context(httpx.AsyncClient())
            pool = await stack.enter_async_context(checkpoint_pool(url))
            policy = config.providers.lexi
            lexicon = Lexicon(
                db_url=url,
                db_schema="lexi",
                llm_config=LLMConfig(
                    model=policy.model,
                    api_key=deployment.inference_api_key.get_secret_value(),
                    base_url=deployment.inference_base_url,
                    timeout=policy.timeout_seconds,
                    max_completion_tokens=policy.max_completion_tokens,
                    reasoning_effort=policy.reasoning_effort,
                    structured_outputs=policy.structured_outputs,
                    temperature=policy.temperature,
                    max_retries=policy.max_retries,
                ),
                decision_config=DecisionConfig(
                    policy.decision_threshold,
                    model=policy.decision_model,
                    base_url=deployment.decision_base_url,
                    api_key=deployment.decision_api_key.get_secret_value(),
                ),
                decision_fallback_model=policy.decision_fallback_model,
            )
            stack.push_async_callback(lexicon.close)
            await lexicon.start()
            generations = Generations(lexicon, config)
            stack.push_async_callback(generations.close)
        except Exception:
            raise RuntimeError(
                "Runtime initialization failed; verify deployment, reference dataset, "
                "PostgreSQL/Redis and explicit migration gate"
            ) from None
        yield SimpleNamespace(
            engine=engine,
            sessions=sessions,
            redis=redis,
            cache=cache,
            http=http,
            lexicon=lexicon,
            generations=generations,
            checkpoint_pool=pool,
        )
    finally:
        try:
            # ExitStack runs every registered closer even when one closer fails.
            await stack.aclose()
        except Exception:
            raise RuntimeError("Runtime resource cleanup failed") from None


async def session(request: Request):
    async with request.app.state.sessions() as connection:
        try:
            yield connection
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "57014":
                raise Problem(503, "query_timeout") from None
            raise


def product(request: Request) -> ProductConfig:
    return request.app.state.product


def lexicon(request: Request) -> Lexicon:
    return request.app.state.lexicon


Session = Annotated[AsyncSession, Depends(session)]
Product = Annotated[ProductConfig, Depends(product)]
Dictionary = Annotated[Lexicon, Depends(lexicon)]
