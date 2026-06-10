"""Authenticated user's own account data + study preferences.

GDPR export, term notes, daily goal, and CEFR thresholds for the calling
user. Split out of the former me_extras junk-drawer; paths + UserDep preserved.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services.cefr_threshold_service import (
    get_thresholds as cefr_get,
)
from pycil_core.services.cefr_threshold_service import (
    set_thresholds as cefr_set,
)
from pycil_core.services.daily_goal_service import (
    goal_summary,
    update_goal,
)
from pycil_core.services.data_export_service import export as ndjson_export
from pycil_core.services.feature_flag_service import is_enabled as flag_enabled
from pycil_core.services.term_notes_service import (
    delete as note_delete,
)
from pycil_core.services.term_notes_service import (
    get as note_get,
)
from pycil_core.services.term_notes_service import (
    upsert as note_upsert,
)
from pycil_core.services.tos_service import (
    ack as _tos_ack,
)
from pycil_core.services.tos_service import (
    needs_ack as _tos_needs_ack,
)

router = APIRouter(tags=["account"])


# ── GDPR export ────────────────────────────────────────────────────────────


@router.get("/me/data-export")
async def export_my_data(user: UserDep, session: SessionDep):
    return StreamingResponse(
        ndjson_export(session, user.id),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="pycil-export.ndjson"'},
    )


# ── Term notes ──────────────────────────────────────────────────────────────


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


# ── ToS gating ─────────────────────────────────────────────────────────────


@router.get("/tos/needs-ack")
async def tos_needs_ack(user: UserDep, session: SessionDep):
    pending = await _tos_needs_ack(session, user.id)
    if not pending:
        return {"needs_ack": False}
    return {
        "needs_ack": True,
        "version": pending.version,
        "summary": pending.summary,
    }


@router.post("/tos/{version}/ack")
async def tos_ack(version: str, user: UserDep, session: SessionDep):
    await _tos_ack(session, user.id, version)
    await session.commit()
    return {"ack": True, "version": version}


# ── Feature flag eval (current user) ────────────────────────────────────────


@router.get("/flags/{name}")
async def get_flag(name: str, user: UserDep, session: SessionDep):
    enabled = await flag_enabled(session, name, user.id)
    return {"name": name, "enabled": enabled}
