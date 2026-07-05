"""FastAPI application factory + startup lifecycle.

At startup the shared ``InProcessLexiClient`` is built and ``lexicon.init()``
runs once (idempotent) so lexi-ai's own DB schema exists. The API is read/enqueue
only — generation runs in the worker (single writer) — so the API's Lexicon is
not used to generate; init just guarantees the schema for read paths.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from pycil.auth.router import router as auth_router
from pycil.common.errors import AppError, app_error_handler
from pycil.common.middleware import install_middleware
from pycil.content.deps import get_lexi_client
from pycil.content.router import router as content_router
from pycil.hierarchy.router import router as hierarchy_router
from pycil.learning.router import router as learning_router
from pycil.realtime.router import router as realtime_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the shared LexiClient and ensure lexi's schema exists. Best-effort:
    # a missing Cambridge file or unreachable lexi DB degrades search/resolve to
    # empty rather than crashing the API — the worker also runs init.
    try:
        await get_lexi_client().init()  # idempotent lexi schema create
    except Exception:  # noqa: BLE001 - startup must not crash on lexi unavailability
        pass
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Pycil API", version="0.1.0", lifespan=lifespan)
    install_middleware(app)
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(auth_router)
    app.include_router(content_router)
    app.include_router(hierarchy_router)
    app.include_router(learning_router)
    app.include_router(realtime_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
