"""API resource lifespan and business routes. Importing never performs I/O."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException

from pycil.account.api import public_router
from pycil.account.api import router as account_router
from pycil.app.config import load_config
from pycil.app.http import (
    BodyLimit,
    ErrorResponse,
    Problem,
    RequestBoundary,
    RuntimeCORS,
    http_error_response,
    problem_response,
    validation_response,
)
from pycil.app.resources import process_resources
from pycil.app.settings import Deployment
from pycil.assistant.api import router as assistant_router
from pycil.infrastructure.clerk import Identity
from pycil.infrastructure.observability import configure_logging, get_logger
from pycil.library.api import router as library_router
from pycil.library.search import router as discovery_router
from pycil.study.api import router as study_router
from pycil.vocabulary.api import router as vocabulary_router

logger = get_logger(__name__)


def create_app() -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        configure_logging()
        config = load_config()
        deployment = Deployment.from_environment()
        async with process_resources(config, deployment) as resources:
            app.state.config = config
            app.state.deployment = deployment
            app.state.identity = Identity(
                deployment,
                timeout=config.runtime.identity.jwks_timeout_seconds,
                lifespan=config.runtime.identity.jwks_lifespan_seconds,
            )
            for name, value in vars(resources).items():
                setattr(app.state, name, value)
            try:
                logger.info("app_startup_completed")
                yield
            finally:
                # Closed clients must not remain accessible after shutdown/restart.
                for name in (*vars(resources), "identity", "config", "deployment"):
                    delattr(app.state, name)
        logger.info("app_shutdown_completed")

    app = FastAPI(
        title="Pycil",
        version="1.0.0",
        lifespan=lifespan,
        responses={
            status: {"model": ErrorResponse}
            for status in (400, 401, 403, 404, 405, 409, 413, 422, 429, 500, 503)
        },
    )
    from typing import cast

    from starlette.types import ExceptionHandler

    app.add_exception_handler(Problem, cast(ExceptionHandler, problem_response))
    app.add_exception_handler(RequestValidationError, cast(ExceptionHandler, validation_response))
    app.add_exception_handler(HTTPException, cast(ExceptionHandler, http_error_response))
    app.include_router(account_router)
    app.include_router(public_router)
    app.include_router(library_router)
    app.include_router(discovery_router)
    app.include_router(vocabulary_router)
    app.include_router(study_router)
    app.include_router(assistant_router)

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    async def ready():
        component = "lifecycle"
        try:
            async with asyncio.timeout(app.state.config.runtime.health.timeout_seconds):
                component = "database"
                async with app.state.engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                component = "redis"
                async with asyncio.timeout(app.state.config.runtime.health.redis_timeout_seconds):
                    await app.state.redis.ping()
                component = "search"
                app.state.search.ready()
        except Exception as error:
            logger.warning(
                "readiness_check_failed",
                component=component,
                error_type=type(error).__name__,
            )
            raise Problem(503, "not_ready") from None
        return {"status": "ready"}

    app.add_middleware(BodyLimit)
    app.add_middleware(RequestBoundary)
    # CORS wraps safe-error middleware, including its 500/413 responses.
    app.add_middleware(RuntimeCORS)
    return app
