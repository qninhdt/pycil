"""Owner-scoped assistant model and thread endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.account.auth import current_user
from pycil.account.schemas import CurrentUser
from pycil.assistant import threads
from pycil.assistant.schemas import ModelCatalogRead, ThreadCreate, ThreadRead, ThreadStateRead
from pycil.assistant.thread_access import refresh_retention, require_owned_thread
from pycil.assistant.turns.leases import lease_ttl_seconds, thread_lease_key
from pycil.assistant.turns.stream import register_turn_routes
from pycil.platform.database import get_session
from pycil.platform.errors import ConflictError, ServiceUnavailableError
from pycil.platform.redis import acquire_lease, get_redis, release_lease

__all__ = ["router"]

router = APIRouter(prefix="/assistant", tags=["assistant"])
register_turn_routes(router)


def _graph(request: Request):
    graph = getattr(request.app.state, "assistant_graph", None)
    if graph is None:
        raise ServiceUnavailableError("assistant_not_configured", code="assistant_not_configured")
    return graph


@router.get("/models", response_model=ModelCatalogRead)
async def list_models(user: CurrentUser = Depends(current_user)) -> ModelCatalogRead:
    del user
    return ModelCatalogRead.from_config()


@router.post("/threads", response_model=ThreadRead, status_code=201)
async def create_thread(
    body: ThreadCreate,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ThreadRead:
    thread = await threads.create_thread(session, owner_id=user.id, title=body.title)
    return ThreadRead.model_validate(thread)


@router.get("/threads", response_model=list[ThreadRead])
async def list_threads(
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ThreadRead]:
    rows = await threads.list_active_threads(session, owner_id=user.id)
    return [ThreadRead.model_validate(row) for row in rows]


@router.get("/threads/{thread_id}", response_model=ThreadRead)
async def get_thread(
    thread_id: UUID,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ThreadRead:
    thread = await require_owned_thread(session, thread_id, user.id)
    await refresh_retention(session, thread)
    return ThreadRead.model_validate(thread)


@router.get("/threads/{thread_id}/state", response_model=ThreadStateRead)
async def get_thread_state(
    thread_id: UUID,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ThreadStateRead:
    await require_owned_thread(session, thread_id, user.id)
    state = await threads.read_state(_graph(request), user.id, thread_id)
    state.status = "interrupted" if state.interrupts else "idle"
    return state


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: UUID,
    request: Request,
    user: CurrentUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> None:
    thread = await require_owned_thread(session, thread_id, user.id)
    key = thread_lease_key(thread_id)
    token = await acquire_lease(redis, key, lease_ttl_seconds())
    if token is None:
        raise ConflictError("assistant_turn_in_progress")
    try:
        await threads.delete_thread(
            session,
            thread,
            getattr(request.app.state, "assistant_checkpointer", None),
        )
    finally:
        await release_lease(redis, key, token)
