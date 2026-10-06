"""API resource lifespan and business routes. Importing never performs I/O."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException

from pycil.account.api import public_router
from pycil.account.api import router as account_router
from pycil.account.auth import Identity
from pycil.assistant.api import router as assistant_router
from pycil.config import Deployment, load_config
from pycil.dependencies import process_resources
from pycil.http import (
    BodyLimit,
    ErrorResponse,
    Problem,
    RequestBoundary,
    RuntimeCORS,
    http_error_response,
    problem_response,
    validation_response,
)
from pycil.library.api import router as library_router
from pycil.library.search import router as discovery_router
from pycil.study.api import router as study_router
from pycil.vocabulary.api import router as vocabulary_router


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        config = load_config()
        deployment = Deployment.from_environment()
        async with process_resources(config, deployment) as resources:
            app.state.product = config
            app.state.deployment = deployment
            app.state.identity = Identity(deployment)
            for name, value in vars(resources).items():
                setattr(app.state, name, value)
            try:
                yield
            finally:
                # Closed clients must not remain accessible after shutdown/restart.
                for name in (*vars(resources), "identity", "product", "deployment"):
                    delattr(app.state, name)

    app = FastAPI(
        title="Pycil",
        version="1.0.0",
        lifespan=lifespan,
        responses={
            status: {"model": ErrorResponse}
            for status in (400, 401, 403, 404, 405, 409, 413, 422, 429, 500, 503)
        },
    )
    app.add_exception_handler(Problem, problem_response)
    app.add_exception_handler(RequestValidationError, validation_response)
    app.add_exception_handler(HTTPException, http_error_response)
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
        try:
            async with app.state.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            await app.state.redis.ping()
        except Exception:
            raise Problem(503, "not_ready") from None
        return {"status": "ready"}

    app.add_middleware(BodyLimit)
    app.add_middleware(RequestBoundary)
    # CORS wraps safe-error middleware, including its 500/413 responses.
    app.add_middleware(RuntimeCORS)
    return app


app = create_app()
