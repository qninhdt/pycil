"""Power-user + social + push routes (P9-P12 batch).

Mounts the public surface for the new services:
- /me/data-export        : streamed NDJSON GDPR export (P12.1)
- /me/follow/{username}   : toggle follow (P9.3)
- /decks/{id}/like        : toggle like (P9.2)
- /push/subscribe         : register push subscription (P4.3)
- /tos/needs-ack          : returns latest unack'd ToS for user (P12.3)
- /tos/{version}/ack      : record ack
- /me/notes/{term_id}     : term notes CRUD (P10.2)
- /flags/{name}           : feature flag eval for current user (P6.2)
- /admin/audit            : list recent admin_actions (P12.2)
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pycil_core.api.deps import RedisDep, SessionDep, UserDep
from pycil_core.services.activity_feed_service import (
    list_for_followees as feed_list_followees,
)
from pycil_core.services.cefr_threshold_service import (
    get_thresholds as cefr_get,
    set_thresholds as cefr_set,
)
from pycil_core.services.daily_goal_service import (
    goal_summary,
    update_goal,
)
from pycil_core.services.data_export_service import export as ndjson_export
from pycil_core.services.feature_flag_service import is_enabled as flag_enabled
from pycil_core.services.push_notification_service import (
    subscribe as push_subscribe_,
    unsubscribe as push_unsubscribe_,
)
from pycil_core.services.social_service import (
    toggle_follow,
    toggle_like,
)
from pycil_core.services.term_notes_service import (
    delete as note_delete,
    get as note_get,
    upsert as note_upsert,
)
from pycil_core.services.tos_service import (
    ack as tos_ack_,
    needs_ack,
)

router = APIRouter(tags=["batch-routes"])


# ── GDPR export ────────────────────────────────────────────────────────────


@router.get("/me/data-export")
async def export_my_data(user: UserDep, session: SessionDep):
    return StreamingResponse(
        ndjson_export(session, user.id),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="pycil-export.ndjson"'},
    )


# ── Social: follow + like ──────────────────────────────────────────────────


class UsernameLookup(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)


@router.post("/me/follow/{username}")
async def toggle_follow_by_username(
    username: str,
    user: UserDep,
    session: SessionDep,
):
    from sqlalchemy import text

    target = (
        await session.execute(
            text("SELECT id FROM users WHERE LOWER(username) = :n"),
            {"n": username.lower()},
        )
    ).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    now_following = await toggle_follow(session, user.id, target.id)
    await session.commit()
    return {"following": now_following}


@router.post("/decks/{deck_id}/like")
async def toggle_deck_like(
    deck_id: UUID,
    user: UserDep,
    session: SessionDep,
):
    liked = await toggle_like(session, user.id, deck_id)
    await session.commit()
    return {"liked": liked}


# ── Push subscriptions ─────────────────────────────────────────────────────


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


# ── ToS gating ─────────────────────────────────────────────────────────────


@router.get("/tos/needs-ack")
async def tos_needs_ack(user: UserDep, session: SessionDep):
    pending = await needs_ack(session, user.id)
    if not pending:
        return {"needs_ack": False}
    return {
        "needs_ack": True,
        "version": pending.version,
        "summary": pending.summary,
    }


@router.post("/tos/{version}/ack")
async def tos_ack(version: str, user: UserDep, session: SessionDep):
    await tos_ack_(session, user.id, version)
    await session.commit()
    return {"ack": True, "version": version}


# ── Term notes ────────────────────────────────────────────────────────────


class TermNotePayload(BaseModel):
    body: str = Field(..., max_length=8192)


@router.get("/me/notes/{term_id}")
async def get_term_note(term_id: int, user: UserDep, session: SessionDep):
    body = await note_get(session, user.id, term_id)
    return {"body": body}


@router.put("/me/notes/{term_id}")
async def put_term_note(
    term_id: int,
    payload: TermNotePayload,
    user: UserDep,
    session: SessionDep,
):
    await note_upsert(session, user.id, term_id, payload.body)
    await session.commit()
    return {"saved": True}


@router.delete("/me/notes/{term_id}")
async def delete_term_note(
    term_id: int, user: UserDep, session: SessionDep
):
    await note_delete(session, user.id, term_id)
    await session.commit()
    return {"deleted": True}


# ── Daily goal + CEFR thresholds ──────────────────────────────────────────


class GoalPayload(BaseModel):
    daily_goal: int | None = Field(default=None, ge=1, le=500)
    reminder_hour: int | None = Field(default=None, ge=0, le=23)


@router.get("/me/goal")
async def my_goal(user: UserDep, session: SessionDep):
    s = await goal_summary(session, user.id)
    return {
        "daily_goal": s.daily_goal,
        "answered_today": s.answered_today,
        "correct_today": s.correct_today,
        "streak_days": s.streak_days,
    }


@router.patch("/me/goal")
async def update_my_goal(
    payload: GoalPayload, user: UserDep, session: SessionDep
):
    await update_goal(
        session,
        user.id,
        daily_goal=payload.daily_goal,
        reminder_hour=payload.reminder_hour,
    )
    await session.commit()
    return await my_goal(user, session)


class ThresholdsPayload(BaseModel):
    thresholds: Annotated[dict[str, int], Field(...)]


@router.get("/me/cefr-thresholds")
async def get_cefr_thresholds(user: UserDep, session: SessionDep):
    return await cefr_get(session, user.id)


@router.put("/me/cefr-thresholds")
async def put_cefr_thresholds(
    payload: ThresholdsPayload, user: UserDep, session: SessionDep
):
    await cefr_set(session, user.id, payload.thresholds)
    await session.commit()
    return await cefr_get(session, user.id)


# ── Activity feed ─────────────────────────────────────────────────────────


@router.get("/me/feed")
async def my_feed(user: UserDep, session: SessionDep, limit: int = 50):
    events = await feed_list_followees(
        session, user.id, limit=min(limit, 200)
    )
    return {"events": events}


# ── Feature flag eval ─────────────────────────────────────────────────────


@router.get("/flags/{name}")
async def get_flag(
    name: str, user: UserDep, session: SessionDep
):
    enabled = await flag_enabled(session, name, user.id)
    return {"name": name, "enabled": enabled}


# ── Admin audit (read-only here; writes go through admin_audit_service) ──


@router.get("/admin/audit")
async def list_audit(
    user: UserDep,
    session: SessionDep,
    limit: int = 100,
):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin_required")
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                "SELECT id, actor_user_id, target_user_id, action, metadata, "
                "created_at, ip_address::text AS ip_address "
                "FROM admin_actions ORDER BY created_at DESC LIMIT :n"
            ),
            {"n": min(limit, 500)},
        )
    ).all()
    return {"actions": [dict(r._mapping) for r in rows]}
