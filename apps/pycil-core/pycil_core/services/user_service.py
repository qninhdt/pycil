"""User upsert + token-version checks for auth.

`upsert_user` is called by Next.js Auth.js `signIn` callback (via internal
`/auth/upsert-user`). It returns the canonical pycil-core `users.id` UUID
that becomes the JWT `sub`.

`get_with_token_version_check` re-reads `users` on every authenticated
request (60s Redis cache layered on top elsewhere) and verifies the JWT
`tv` claim matches `users.token_version` for lightweight per-user
revocation.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared.db import User
from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def upsert_user(
    session: AsyncSession,
    *,
    email: str,
    name: str | None,
    image: str | None,
) -> UUID:
    """Idempotently insert or update a `users` row keyed by email.

    Returns the row's UUID.
    """
    stmt = insert(User).values(email=email, name=name, image=image)
    row = (
        await session.exec(
            stmt.on_conflict_do_update(
                index_elements=[User.email],
                set_={
                    "name": func.coalesce(stmt.excluded.name, User.name),
                    "image": func.coalesce(stmt.excluded.image, User.image),
                },
            ).returning(User.id)
        )
    ).one()
    await session.commit()
    return row[0] if isinstance(row, tuple) else row.id


async def get_with_token_version_check(
    session: AsyncSession,
    *,
    user_id: UUID,
    token_version: int,
) -> dict | None:
    """Return user fields if id exists and `token_version` matches.

    Returns None if user is gone or token_version mismatches.
    """
    row = (
        await session.exec(
            select(User).where(User.id == user_id).limit(1)
        )
    ).first()
    if row is None:
        return None
    if row.token_version != token_version:
        return None
    return {
        "id": row.id,
        "email": row.email,
        "name": row.name,
        "image": row.image,
    }


async def revoke_tokens(
    session: AsyncSession, *, user_id: UUID
) -> int:
    """Bump token_version. Returns the new version. Used by 'sign out everywhere'."""
    row = (
        await session.exec(
            update(User)
            .where(User.id == user_id)
            .values(token_version=User.token_version + 1, updated_at=func.now())
            .returning(User.token_version)
        )
    ).first()
    if row is None:
        raise LookupError("user_not_found")
    await session.commit()
    return int(row[0] if isinstance(row, tuple) else row.token_version)


async def soft_delete_user(session: AsyncSession, *, user_id: UUID) -> None:
    """Mark user deleted_at=NOW() and revoke tokens. Cron hard-deletes after 14d."""
    await session.exec(
        update(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .values(
            deleted_at=func.now(),
            token_version=User.token_version + 1,
            updated_at=func.now(),
        )
    )
    await session.commit()


async def hard_delete_expired(session: AsyncSession) -> int:
    """Permanently delete users soft-deleted >14 days ago. Returns count."""
    cutoff = datetime.now(UTC) - timedelta(days=14)
    result = await session.exec(
        delete(User).where(User.deleted_at.is_not(None), User.deleted_at < cutoff)
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def is_soft_deleted(
    session: AsyncSession, *, email: str
) -> bool:
    """Used by upsert flow to reject sign-in for soft-deleted accounts."""
    deleted_at = (
        await session.exec(select(User.deleted_at).where(User.email == email))
    ).first()
    return deleted_at is not None
