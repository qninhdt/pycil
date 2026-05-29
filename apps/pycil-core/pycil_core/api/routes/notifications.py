"""Notifications HTTP API: list, mark-read, unread count."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: str
    kind: str
    payload: dict
    read_at: str | None
    created_at: str


class MarkReadBody(BaseModel):
    ids: list[UUID]


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    user: UserDep,
    session: SessionDep,
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[NotificationOut]:
    rows = await notification_service.list_for_user(
        session, user_id=user.id, since=since, limit=limit
    )
    return [NotificationOut(**r) for r in rows]


@router.get("/unread-count")
async def unread_count(user: UserDep, session: SessionDep) -> dict[str, int]:
    n = await notification_service.unread_count(session, user_id=user.id)
    return {"count": n}


@router.post("/mark-read")
async def mark_read(
    body: MarkReadBody, user: UserDep, session: SessionDep
) -> dict[str, int]:
    if len(body.ids) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "too_many_ids")
    n = await notification_service.mark_read(
        session, user_id=user.id, ids=body.ids
    )
    return {"updated": n}
