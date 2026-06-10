"""Social routes: follow/unfollow, deck like toggle, activity feed.

Split out of the former me_extras junk-drawer; paths + UserDep preserved.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from shared.db import User
from sqlalchemy import func
from sqlmodel import select

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services.activity_feed_service import (
    list_for_followees as feed_list_followees,
)
from pycil_core.services.social_service import (
    toggle_follow,
    toggle_like,
)

router = APIRouter(tags=["social"])


@router.post("/me/follow/{username}")
async def toggle_follow_by_username(
    username: str,
    user: UserDep,
    session: SessionDep,
):
    target_id = (
        await session.exec(
            select(User.id).where(func.lower(User.username) == username.lower())
        )
    ).first()
    if not target_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    now_following = await toggle_follow(session, user.id, target_id)
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


@router.get("/me/feed")
async def my_feed(user: UserDep, session: SessionDep, limit: int = 50):
    events = await feed_list_followees(
        session, user.id, limit=min(limit, 200)
    )
    return {"events": events}
