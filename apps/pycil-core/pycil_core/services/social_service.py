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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
    existing = (
        await session.execute(
            text("SELECT id FROM users WHERE LOWER(username) = :n"),
            {"n": name},
        )
    ).first()
    if existing and existing.id != user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "username_taken")
    await session.execute(
        text("UPDATE users SET username = :n WHERE id = :id"),
        {"n": name, "id": user_id},
    )
    return name


async def toggle_follow(
    session: AsyncSession, follower_id: UUID, followee_id: UUID
) -> bool:
    """Returns True if now following, False if unfollowed."""
    if follower_id == followee_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot_follow_self")
    existing = (
        await session.execute(
            text(
                "SELECT 1 FROM follows "
                "WHERE follower_id = :f AND followee_id = :t"
            ),
            {"f": follower_id, "t": followee_id},
        )
    ).first()
    if existing:
        await session.execute(
            text(
                "DELETE FROM follows "
                "WHERE follower_id = :f AND followee_id = :t"
            ),
            {"f": follower_id, "t": followee_id},
        )
        return False
    await session.execute(
        text(
            "INSERT INTO follows (follower_id, followee_id) "
            "VALUES (:f, :t) ON CONFLICT DO NOTHING"
        ),
        {"f": follower_id, "t": followee_id},
    )
    return True


async def toggle_like(
    session: AsyncSession, user_id: UUID, deck_id: UUID
) -> bool:
    existing = (
        await session.execute(
            text(
                "SELECT 1 FROM deck_likes "
                "WHERE user_id = :u AND deck_id = :d"
            ),
            {"u": user_id, "d": deck_id},
        )
    ).first()
    if existing:
        await session.execute(
            text(
                "DELETE FROM deck_likes "
                "WHERE user_id = :u AND deck_id = :d"
            ),
            {"u": user_id, "d": deck_id},
        )
        await session.execute(
            text(
                "UPDATE nodes SET likes_count = GREATEST(0, likes_count - 1) "
                "WHERE id = :d"
            ),
            {"d": deck_id},
        )
        return False
    await session.execute(
        text(
            "INSERT INTO deck_likes (user_id, deck_id) "
            "VALUES (:u, :d) ON CONFLICT DO NOTHING"
        ),
        {"u": user_id, "d": deck_id},
    )
    await session.execute(
        text("UPDATE nodes SET likes_count = likes_count + 1 WHERE id = :d"),
        {"d": deck_id},
    )
    return True


async def record_fork(session: AsyncSession, source_deck_id: UUID) -> None:
    await session.execute(
        text("UPDATE nodes SET forks_count = forks_count + 1 WHERE id = :d"),
        {"d": source_deck_id},
    )
