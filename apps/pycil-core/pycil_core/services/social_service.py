"""Public profile + social services (P9 phases 1-3).

- ensure_username: enforce uniqueness + reserved-name list when user
  flips visibility to public.
- toggle_follow: add/remove follow row, idempotent.
- toggle_like:   add/remove deck like, bumps nodes.likes_count.
- record_fork:   on deep_clone, bump source nodes.forks_count.
"""
from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel.ext.asyncio.session import AsyncSession

from shared.db import DeckLike, Follow, Node, User

_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,32}$")
_RESERVED = {"admin", "support", "system", "api", "pycil", "root", "anonymous"}


async def claim_username(
    session: AsyncSession, user_id: UUID, username: str
) -> str:
    name = username.lower().strip()
    if not _USERNAME_RE.match(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username_invalid")
    if name in _RESERVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "username_reserved")
    existing_id = (
        await session.exec(
            select(User.id).where(func.lower(User.username) == name)
        )
    ).first()
    if existing_id and existing_id != user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")
    await session.exec(
        update(User).where(User.id == user_id).values(username=name)
    )
    return name


async def toggle_follow(
    session: AsyncSession, follower_id: UUID, followee_id: UUID
) -> bool:
    """Returns True if now following, False if unfollowed."""
    if follower_id == followee_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_follow_self")
    existing = (
        await session.exec(
            select(Follow.follower_id).where(
                Follow.follower_id == follower_id,
                Follow.followee_id == followee_id,
            )
        )
    ).first()
    if existing:
        await session.exec(
            delete(Follow).where(
                Follow.follower_id == follower_id,
                Follow.followee_id == followee_id,
            )
        )
        return False
    await session.exec(
        insert(Follow)
        .values(follower_id=follower_id, followee_id=followee_id)
        .on_conflict_do_nothing(
            index_elements=[Follow.follower_id, Follow.followee_id]
        )
    )
    return True


async def toggle_like(
    session: AsyncSession, user_id: UUID, deck_id: UUID
) -> bool:
    existing = (
        await session.exec(
            select(DeckLike.user_id).where(
                DeckLike.user_id == user_id,
                DeckLike.deck_id == deck_id,
            )
        )
    ).first()
    if existing:
        await session.exec(
            delete(DeckLike).where(
                DeckLike.user_id == user_id,
                DeckLike.deck_id == deck_id,
            )
        )
        await session.exec(
            update(Node)
            .where(Node.id == deck_id)
            .values(likes_count=func.greatest(0, Node.likes_count - 1))
        )
        return False
    inserted = await session.exec(
        insert(DeckLike)
        .values(user_id=user_id, deck_id=deck_id)
        .on_conflict_do_nothing(
            index_elements=[DeckLike.user_id, DeckLike.deck_id]
        )
        .returning(DeckLike.user_id)
    )
    if inserted.first() is not None:
        await session.exec(
            update(Node)
            .where(Node.id == deck_id)
            .values(likes_count=Node.likes_count + 1)
        )
    return True


async def record_fork(session: AsyncSession, source_deck_id: UUID) -> None:
    await session.exec(
        update(Node)
        .where(Node.id == source_deck_id)
        .values(forks_count=Node.forks_count + 1)
    )
