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

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
    row = (
        await session.execute(
            text(
                """
                INSERT INTO users (email, name, image)
                VALUES (:email, :name, :image)
                ON CONFLICT (email) DO UPDATE
                SET name = COALESCE(EXCLUDED.name, users.name),
                    image = COALESCE(EXCLUDED.image, users.image)
                RETURNING id
                """
            ),
            {"email": email, "name": name, "image": image},
        )
    ).one()
    await session.commit()
    return row.id


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
        await session.execute(
            text(
                """
                SELECT id, email, name, image, token_version
                FROM users
                WHERE id = :uid
                LIMIT 1
                """
            ),
            {"uid": user_id},
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
        await session.execute(
            text(
                """
                UPDATE users
                   SET token_version = token_version + 1,
                       updated_at = NOW()
                 WHERE id = :uid
                RETURNING token_version
                """
            ),
            {"uid": user_id},
        )
    ).first()
    if row is None:
        raise LookupError("user_not_found")
    await session.commit()
    return int(row.token_version)


async def soft_delete_user(session: AsyncSession, *, user_id: UUID) -> None:
    """Mark user deleted_at=NOW() and revoke tokens. Cron hard-deletes after 14d."""
    await session.execute(
        text(
            """
            UPDATE users
               SET deleted_at = NOW(),
                   token_version = token_version + 1,
                   updated_at = NOW()
             WHERE id = :uid AND deleted_at IS NULL
            """
        ),
        {"uid": user_id},
    )
    await session.commit()


async def hard_delete_expired(session: AsyncSession) -> int:
    """Permanently delete users soft-deleted >14 days ago. Returns count."""
    result = await session.execute(
        text(
            """
            DELETE FROM users
             WHERE deleted_at IS NOT NULL
               AND deleted_at < NOW() - INTERVAL '14 days'
            """
        )
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def is_soft_deleted(
    session: AsyncSession, *, email: str
) -> bool:
    """Used by upsert flow to reject sign-in for soft-deleted accounts."""
    row = (
        await session.execute(
            text("SELECT deleted_at FROM users WHERE email = :email"),
            {"email": email},
        )
    ).first()
    return row is not None and row.deleted_at is not None
