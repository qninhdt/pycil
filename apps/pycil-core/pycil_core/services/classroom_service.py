"""Classroom service (P9 phase 4).

Teacher-led shared spaces for classroom_decks. Lightweight ACL: owner
+ teachers can invite/remove students; students can list assigned decks
and clone them. Join via short code.
"""
from __future__ import annotations

import secrets
import string
from typing import Sequence
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


JOIN_CODE_LEN = 8
_JOIN_ALPHABET = string.ascii_uppercase + string.digits


def _generate_join_code() -> str:
    return "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(JOIN_CODE_LEN))


async def create(
    session: AsyncSession, owner_id: UUID, name: str, max_students: int = 50
) -> dict:
    code = _generate_join_code()
    row = (
        await session.execute(
            text(
                """
                INSERT INTO classrooms (owner_id, name, join_code, max_students)
                VALUES (:o, :n, :c, :m)
                RETURNING id, join_code
                """
            ),
            {"o": owner_id, "n": name, "c": code, "m": max(1, min(500, max_students))},
        )
    ).one()
    await session.execute(
        text(
            "INSERT INTO classroom_members (classroom_id, user_id, role) "
            "VALUES (:cls, :u, 'teacher')"
        ),
        {"cls": row.id, "u": owner_id},
    )
    return {"id": str(row.id), "join_code": row.join_code}


async def join_with_code(
    session: AsyncSession, user_id: UUID, code: str
) -> UUID:
    row = (
        await session.execute(
            text("SELECT id, max_students FROM classrooms WHERE join_code = :c"),
            {"c": code.upper()},
        )
    ).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "classroom_not_found")
    count = (
        await session.execute(
            text(
                "SELECT COUNT(*)::int AS n FROM classroom_members "
                "WHERE classroom_id = :c AND role = 'student'"
            ),
            {"c": row.id},
        )
    ).one()
    if int(count.n) >= int(row.max_students):
        raise HTTPException(status.HTTP_409_CONFLICT, "classroom_full")
    await session.execute(
        text(
            "INSERT INTO classroom_members (classroom_id, user_id, role) "
            "VALUES (:c, :u, 'student') ON CONFLICT DO NOTHING"
        ),
        {"c": row.id, "u": user_id},
    )
    return row.id


async def assign_deck(
    session: AsyncSession,
    actor_id: UUID,
    classroom_id: UUID,
    deck_id: UUID,
) -> None:
    role = (
        await session.execute(
            text(
                "SELECT role FROM classroom_members "
                "WHERE classroom_id = :c AND user_id = :u"
            ),
            {"c": classroom_id, "u": actor_id},
        )
    ).first()
    if not role or role.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "classroom_assign_forbidden")
    await session.execute(
        text(
            "INSERT INTO classroom_decks (classroom_id, deck_id) "
            "VALUES (:c, :d) ON CONFLICT DO NOTHING"
        ),
        {"c": classroom_id, "d": deck_id},
    )


async def list_assigned(
    session: AsyncSession, user_id: UUID
) -> Sequence[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT n.id AS deck_id, n.name AS deck_name, c.id AS classroom_id,
                       c.name AS classroom_name
                  FROM classroom_decks cd
                  JOIN classroom_members cm
                    ON cm.classroom_id = cd.classroom_id
                  JOIN classrooms c ON c.id = cd.classroom_id
                  JOIN nodes n ON n.id = cd.deck_id
                 WHERE cm.user_id = :u
                """
            ),
            {"u": user_id},
        )
    ).all()
    return [dict(r._mapping) for r in rows]
