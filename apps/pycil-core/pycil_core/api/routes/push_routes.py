"""Web-push subscription routes (PWA notifications).

Split out of the former me_extras junk-drawer; paths + UserDep preserved.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services.push_notification_service import (
    subscribe as push_subscribe_,
)
from pycil_core.services.push_notification_service import (
    unsubscribe as push_unsubscribe_,
)

router = APIRouter(tags=["push"])


class PushSubscribePayload(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None = None


@router.post("/push/subscribe")
async def push_subscribe(
    payload: PushSubscribePayload,
    user: UserDep,
    session: SessionDep,
):
    sub_id = await push_subscribe_(
        session,
        user.id,
        endpoint=payload.endpoint,
        p256dh=payload.p256dh,
        auth=payload.auth,
        user_agent=payload.user_agent,
    )
    await session.commit()
    return {"subscription_id": sub_id}


@router.delete("/push/subscribe")
async def push_unsubscribe(
    payload: PushSubscribePayload,
    user: UserDep,
    session: SessionDep,
):
    removed = await push_unsubscribe_(
        session, user.id, payload.endpoint
    )
    await session.commit()
    return {"removed": removed}
