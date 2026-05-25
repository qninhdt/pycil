"""FastAPI app entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from pycil_core.api.routes import admin as admin_routes
from pycil_core.api.routes import auth as auth_routes
from pycil_core.api.routes import jobs as jobs_routes
from pycil_core.api.routes import learning as learning_routes
from pycil_core.api.routes import nodes as nodes_routes
from pycil_core.api.routes import onboarding as onboarding_routes
from pycil_core.api.routes import questions as questions_routes
from pycil_core.api.routes import terms as terms_routes
from pycil_core.auth import CurrentUser, get_current_user
from pycil_core.config import get_settings
from pycil_core.cron import get_scheduler
from pycil_core.middleware import OriginAllowlistMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler = get_scheduler()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="pycil-core",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        OriginAllowlistMiddleware,
        allowed_origins=settings.allowed_origins_list,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me")
    async def me(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        return user

    app.include_router(auth_routes.router)
    app.include_router(admin_routes.router)
    app.include_router(nodes_routes.router)
    app.include_router(terms_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(questions_routes.router)
    app.include_router(learning_routes.router)
    app.include_router(onboarding_routes.router)

    return app


app = create_app()
