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
from pycil.app.broker import create_broker
from pycil.app.config import load_config
from pycil.app.http import (
    Problem,
    ProblemDetails,
    RequestBoundary,
    RuntimeCORS,
    http_error_response,
    operation_error_response,
    validation_response,
)
from pycil.app.resources import api_resources
from pycil.app.settings import ApiSettings
from pycil.assistant.api import router as assistant_router
from pycil.infrastructure.clerk import Identity
from pycil.jobs.api import router as jobs_router
from pycil.library.api import discovery_router
from pycil.library.api import router as library_router
from pycil.observability import configure_logging, get_logger
from pycil.observability.http import HttpTelemetry
from pycil.observability.jobs import OpenTelemetryMiddleware
from pycil.study.api import router as study_router
from pycil.utils.errors import OperationError
from pycil.vocabulary.api import router as vocabulary_router

logger = get_logger(__name__)


def create_app() -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        configure_logging()
        config = load_config()
        deployment = ApiSettings.from_environment()
        async with api_resources(config, deployment) as resources:
            app.state.config = config
            app.state.deployment = deployment
            app.state.identity = Identity(
                deployment.clerk_jwks_url,
                deployment.clerk_issuer,
                deployment.clerk_audience,
                timeout=config.account.jwks_timeout_seconds,
                lifespan=config.account.jwks_lifespan_seconds,
            )
            for name, value in vars(resources).items():
                setattr(app.state, name, value)
            app.state.broker = create_broker(config, deployment)
            app.state.broker.add_middlewares(OpenTelemetryMiddleware())
            try:
                await app.state.broker.startup()
                logger.info("app_startup_completed")
                yield
            finally:
                try:
                    await app.state.broker.shutdown()
                finally:
                    del app.state.broker
                    # Closed clients must not remain accessible after shutdown/restart.
                    for name in (*vars(resources), "identity", "config", "deployment"):
                        delattr(app.state, name)
        logger.info("app_shutdown_completed")

    app = FastAPI(
        # Our sanitized ASGI boundary owns HTTP signals and the SDK lifecycle.
        telemetry={
            "auto_configure": False,
            "tracing": False,
            "metrics": False,
            "logs": False,
            "operation_spans": False,
        },
        title="Pycil",
        version="1.0.0",
        lifespan=lifespan,
        responses={
            status: {
                "model": ProblemDetails,
                "content": {
                    "application/problem+json": {"schema": ProblemDetails.model_json_schema()}
                },
            }
            for status in (400, 401, 403, 404, 405, 409, 413, 422, 429, 500, 503)
        },
    )
    from typing import cast

    from starlette.types import ExceptionHandler

    app.add_exception_handler(OperationError, cast(ExceptionHandler, operation_error_response))
    app.add_exception_handler(RequestValidationError, cast(ExceptionHandler, validation_response))
    app.add_exception_handler(HTTPException, cast(ExceptionHandler, http_error_response))
    app.include_router(account_router)
    app.include_router(public_router)
    app.include_router(library_router)
    app.include_router(discovery_router)
    app.include_router(vocabulary_router)
    app.include_router(jobs_router)
    app.include_router(study_router)
    app.include_router(assistant_router)

    @app.get("/livez", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def ready() -> dict[str, str]:
        component = "lifecycle"
        try:
            async with asyncio.timeout(app.state.config.system.health.timeout_seconds):
                component = "database"
                async with app.state.engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                component = "kv_store"
                async with asyncio.timeout(app.state.config.system.health.redis_timeout_seconds):
                    await app.state.redis.ping()
                component = "search"
                await app.state.search.health()
        except Exception as error:
            logger.warning(
                "readiness_check_failed",
                component=component,
                error_type=type(error).__name__,
            )
            raise Problem(503, "not_ready") from None
        return {"status": "ready"}

    app.add_middleware(RequestBoundary)
    # CORS wraps safe-error middleware, including its 500/413 responses.
    app.add_middleware(RuntimeCORS)
    app.add_middleware(HttpTelemetry)
    return app
