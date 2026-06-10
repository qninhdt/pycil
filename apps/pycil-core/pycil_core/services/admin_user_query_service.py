"""Admin-facing user read-models.

Read-only queries that back the admin user dashboard (search, detail summary,
recent jobs, mastery distribution). Split out of user_service so that module
keeps only the auth/token/ban/GDPR write-path; these are admin-only reads.
"""

from __future__ import annotations

from uuid import UUID

from shared.db import Job, User, UserTermStat
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def search_users(
    session: AsyncSession,
    *,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List users, optionally filtered by case-insensitive email/name/username."""
    stmt = select(
        User.id,
        User.email,
        User.name,
        User.username,
        User.role,
        User.banned_at,
        User.created_at,
    ).where(User.deleted_at.is_(None))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(func.coalesce(User.email, "")).like(like)
            | func.lower(func.coalesce(User.name, "")).like(like)
            | func.lower(func.coalesce(User.username, "")).like(like)
        )
    stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.exec(stmt)).all()
    out: list[dict] = []
    for r in rows:
        role = r.role.value if hasattr(r.role, "value") else str(r.role)
        out.append(
            {
                "id": str(r.id),
                "email": r.email,
                "name": r.name,
                "username": r.username,
                "role": role,
                "banned": r.banned_at is not None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return out


async def get_user_summary(session: AsyncSession, *, user_id: UUID) -> dict | None:
    """Return a single user's admin-facing summary, or None if not found."""
    row = (
        await session.exec(
            select(
                User.id,
                User.email,
                User.name,
                User.username,
                User.role,
                User.banned_at,
                User.ban_reason,
                User.created_at,
                User.token_version,
            ).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        return None
    role = row.role.value if hasattr(row.role, "value") else str(row.role)
    return {
        "id": str(row.id),
        "email": row.email,
        "name": row.name,
        "username": row.username,
        "role": role,
        "banned": row.banned_at is not None,
        "banned_at": row.banned_at.isoformat() if row.banned_at else None,
        "ban_reason": row.ban_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "token_version": int(row.token_version),
    }


async def recent_jobs(
    session: AsyncSession, *, user_id: UUID, limit: int = 10
) -> list[dict]:
    """Most recent jobs created by this user (for the admin detail view)."""
    rows = (
        await session.exec(
            select(Job.id, Job.type, Job.status, Job.created_at)
            .where(Job.created_by_user_id == user_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "type": r.type,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def mastery_distribution(
    session: AsyncSession, *, user_id: UUID
) -> dict[str, int]:
    """Count of `user_term_stats` rows per mastery_level for this user."""
    rows = (
        await session.exec(
            select(UserTermStat.mastery_level, func.count())
            .where(UserTermStat.user_id == user_id)
            .group_by(UserTermStat.mastery_level)
        )
    ).all()
    return {str(level): int(count) for level, count in rows}
