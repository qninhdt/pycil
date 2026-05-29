"""Classroom service (P9 phase 4).

Teacher-led shared spaces for classroom_decks. Lightweight ACL: owner
+ teachers can invite/remove students; students can list assigned decks
and clone them. Join via short code.
"""

from __future__ import annotations

import secrets
import string
from collections.abc import Sequence
from uuid import UUID

from fastapi import HTTPException, status
from shared.db.enums import ClassroomRole
from shared.db.models import Classroom, ClassroomDeck, ClassroomMember, Node
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

JOIN_CODE_LEN = 8
_JOIN_ALPHABET = string.ascii_uppercase + string.digits


def _generate_join_code() -> str:
    return "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(JOIN_CODE_LEN))


async def create(session: AsyncSession, owner_id: UUID, name: str, max_students: int = 50) -> dict:
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


async def join_with_code(session: AsyncSession, user_id: UUID, code: str) -> UUID:
    row = (await session.exec(select(Classroom).where(Classroom.join_code == code.upper()))).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "classroom_not_found")
    count = (
        await session.exec(
            select(func.count()).where(
                ClassroomMember.classroom_id == row.id,
                ClassroomMember.role == ClassroomRole.STUDENT,
            )
        )
    ).one()
    if int(count) >= int(row.max_students):
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
        await session.exec(
            select(ClassroomMember.role).where(
                ClassroomMember.classroom_id == classroom_id,
                ClassroomMember.user_id == actor_id,
            )
        )
    ).first()
    if role != ClassroomRole.TEACHER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "classroom_assign_forbidden")
    await session.execute(
        text(
            "INSERT INTO classroom_decks (classroom_id, deck_id) "
            "VALUES (:c, :d) ON CONFLICT DO NOTHING"
        ),
        {"c": classroom_id, "d": deck_id},
    )


async def list_assigned(session: AsyncSession, user_id: UUID) -> Sequence[dict]:
    stmt = (
        select(
            Node.id.label("deck_id"),
            Node.name.label("deck_name"),
            Classroom.id.label("classroom_id"),
            Classroom.name.label("classroom_name"),
        )
        .join(ClassroomMember, ClassroomMember.classroom_id == ClassroomDeck.classroom_id)
        .join(Classroom, Classroom.id == ClassroomDeck.classroom_id)
        .join(Node, Node.id == ClassroomDeck.deck_id)
        .where(ClassroomMember.user_id == user_id)
    )
    rows = (await session.exec(stmt)).all()
    return [dict(r._mapping) for r in rows]
