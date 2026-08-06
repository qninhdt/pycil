"""FastAPI application factory + startup lifecycle."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from pycil.account_lifecycle.router import router as account_lifecycle_router
from pycil.assistant.application.graph import build_graph
from pycil.assistant.infra.checkpointer import open_checkpointer
from pycil.assistant.router import router as assistant_router
from pycil.auth.deps import current_user
from pycil.auth.router import router as auth_router
from pycil.auth.schemas import CapabilitiesRead, CurrentUser, ViewerRead
from pycil.common.errors import (
    AppError,
    ServiceUnavailableError,
    app_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from pycil.common.middleware import install_middleware
from pycil.config import settings, validate_production_settings
from pycil.content.router import router as content_router
from pycil.db.redis import get_redis
from pycil.db.session import engine
from pycil.hierarchy.router import router as hierarchy_router
from pycil.learning.router import router as learning_router
from pycil.observability import metrics
from pycil.ports.centrifugo import readiness as centrifugo_readiness
from pycil.ports.lexi_provider import close_lexi_client, get_lexi_client
from pycil.realtime.router import router as realtime_router
from pycil.realtime.router import subscribe_proxy_router

_WORKER_HEARTBEAT_KEY = "worker:heartbeat"


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
        app.state.assistant_graph = build_graph(checkpointer)
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
    app.include_router(auth_router, prefix="/v1")
    app.include_router(account_lifecycle_router, prefix="/v1")
    app.include_router(assistant_router, prefix="/v1")
    app.include_router(content_router, prefix="/v1")
    app.include_router(hierarchy_router, prefix="/v1")
    app.include_router(learning_router, prefix="/v1")
    app.include_router(realtime_router, prefix="/v1")
    app.include_router(subscribe_proxy_router)

    @app.get("/v1/me", response_model=ViewerRead)
    async def me(user: CurrentUser = Depends(current_user)) -> ViewerRead:
        # A projection, not the internal CurrentUser: token_version is the auth
        # revocation counter and has no business reaching a browser.
        return ViewerRead(id=user.id, email=user.email, name=user.name, image=user.image)

    @app.get("/v1/capabilities", response_model=CapabilitiesRead)
    async def capabilities() -> CapabilitiesRead:
        return CapabilitiesRead(
            assistant=bool(settings.assistant_api_key and settings.assistant_base_url)
        )

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
            if not await redis.get(_WORKER_HEARTBEAT_KEY):
                raise RuntimeError("worker_heartbeat_missing")
        except Exception as exc:  # noqa: BLE001 - readiness must collapse dependency details
            raise ServiceUnavailableError("core_dependency_unavailable") from exc
        if not await centrifugo_readiness():
            raise ServiceUnavailableError("centrifugo_unavailable")
        return {"status": "ready"}

    @app.get("/internal/metrics", include_in_schema=False)
    async def internal_metrics() -> PlainTextResponse:
        """Internal-secret-protected Prometheus/OpenMetrics scrape endpoint."""
        return PlainTextResponse(
            metrics.render_openmetrics(), media_type="text/plain; version=0.0.4"
        )

    return app


app = create_app()
