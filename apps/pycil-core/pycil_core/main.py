"""FastAPI app entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from pycil_core.api.routes import admin as admin_routes
from pycil_core.api.routes import auth as auth_routes
from pycil_core.api.routes import jobs as jobs_routes
from pycil_core.api.routes import learning as learning_routes
from pycil_core.api.routes import nodes as nodes_routes
from pycil_core.api.routes import notifications as notifications_routes
from pycil_core.api.routes import onboarding as onboarding_routes
from pycil_core.api.routes import question_regenerate as question_regenerate_routes
from pycil_core.api.routes import questions as questions_routes
from pycil_core.api.routes import search as search_routes
from pycil_core.api.routes import share_links as share_links_routes
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
    async def me(user: CurrentUser = Depends(get_current_user)):
        """Returns the canonical user with gamification fields layered in."""
        from sqlalchemy import text
        from pycil_core.db import get_engine
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            row = (
                await session.execute(
                    text(
                        "SELECT image_url, streak_days, xp_total, level, "
                        "badges, league_rank, locale, bio "
                        "FROM users WHERE id = :uid"
                    ),
                    {"uid": user.id},
                )
            ).first()
        return {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "image": user.image,
            "image_url": row.image_url if row else None,
            "streak_days": int(row.streak_days) if row else 0,
            "xp_total": int(row.xp_total) if row else 0,
            "level": int(row.level) if row else 1,
            "badges": (row.badges if row else []) or [],
            "league_rank": int(row.league_rank) if row else 0,
            "locale": (row.locale if row else "en") or "en",
            "bio": row.bio if row else None,
        }

    app.include_router(auth_routes.router)
    app.include_router(admin_routes.router)
    app.include_router(nodes_routes.router)
    app.include_router(terms_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(questions_routes.router)
    app.include_router(question_regenerate_routes.router)
    app.include_router(learning_routes.router)
    app.include_router(notifications_routes.router)
    app.include_router(onboarding_routes.router)
    app.include_router(search_routes.router)
    app.include_router(share_links_routes.router)

    return app


app = create_app()
