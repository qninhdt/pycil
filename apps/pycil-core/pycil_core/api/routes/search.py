"""GET /search?q=&limit= — trigram search across user's content."""
from __future__ import annotations

from fastapi import APIRouter, Query

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    user: UserDep,
    session: SessionDep,
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict:
    return await search_service.search(
        session, user_id=user.id, q=q, limit=limit
    )
