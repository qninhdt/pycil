"""FastAPI application factory + startup lifecycle."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from pycil.account.api import router as account_router
from pycil.assistant.agent.adapter import PycilAgent
from pycil.assistant.agent.graph import build_graph
from pycil.assistant.api import router as assistant_router
from pycil.assistant.checkpointer import open_checkpointer
from pycil.billing.api import router as billing_router
from pycil.jobs.api import router as jobs_router
from pycil.lexicon.api import router as lexicon_router
from pycil.lexicon.provider import close_lexi_client, get_lexi_client
from pycil.library.api import router as library_router
from pycil.platform.database import engine
from pycil.platform.errors import (
    AppError,
    ServiceUnavailableError,
    app_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from pycil.platform.middleware import install_middleware
from pycil.platform.redis import get_redis
from pycil.platform.settings import settings, validate_production_settings
from pycil.platform.telemetry import metrics
from pycil.study.api import router as study_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_settings(settings)
    # Create the embedded reader once per API process, after production config
    # validation but before accepting requests.
    get_lexi_client()
    if settings.assistant_api_key and settings.assistant_base_url:
        pool, checkpointer = await open_checkpointer()
        app.state.assistant_pool = pool
        app.state.assistant_checkpointer = checkpointer
        graph = build_graph(checkpointer)
        app.state.assistant_graph = graph
        # The adapter owns the AG-UI event protocol; Pycil adds durability and
        # the typed request context on top of it.
        app.state.assistant_agent = PycilAgent(name="pycil", graph=graph)
    try:
        yield
    finally:
        await close_lexi_client()
        pool = getattr(app.state, "assistant_pool", None)
        if pool is not None:
            await pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Pycil API", version="0.1.0", lifespan=lifespan)
    install_middleware(app)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    # Registered LAST and broadest. Starlette dispatches by the most specific
    # registered class, so the four above still win for the types they name; this
    # catches everything else, which would otherwise return a bare 500 with no
    # code and no requestId for a client whose error parser keys on `error.code`.
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(account_router, prefix="/v1")
    app.include_router(billing_router, prefix="/v1")
    app.include_router(assistant_router, prefix="/v1")
    app.include_router(lexicon_router, prefix="/v1")
    app.include_router(library_router, prefix="/v1")
    app.include_router(study_router, prefix="/v1")
    app.include_router(jobs_router, prefix="/v1")

    @app.get("/v1/openapi.json", include_in_schema=False)
    async def versioned_openapi() -> JSONResponse:
        """Serve the v1 contract at a stable, versioned URL for API consumers."""
        return JSONResponse(app.openapi())

    @app.get("/health/live")
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness() -> dict[str, str]:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            redis = get_redis()
            await redis.ping()
        except Exception as exc:  # noqa: BLE001 - readiness must collapse dependency details
            raise ServiceUnavailableError("core_dependency_unavailable") from exc
        return {"status": "ready"}

    @app.get("/internal/metrics", include_in_schema=False)
    async def internal_metrics() -> PlainTextResponse:
        """Internal-secret-protected Prometheus/OpenMetrics scrape endpoint."""
        return PlainTextResponse(
            metrics.render_openmetrics(), media_type="text/plain; version=0.0.4"
        )

    return app


app = create_app()
