"""User upsert + token-version checks for auth.

`upsert_user` is called by Next.js Auth.js `signIn` callback (via internal
`/auth/upsert-user`). It returns the canonical pycil-core `users.id` UUID
that becomes the JWT `sub`, plus the current `role` and `token_version` so
the Auth.js `jwt` callback can mint a JWT whose edge claims (`token.role`,
`token.tv`) match the DB on first login.

`get_with_token_version_check` re-reads `users` on every authenticated
request and verifies the JWT `tv` claim matches `users.token_version` for
lightweight per-user revocation. It also surfaces `role` + `banned_at` so the
auth layer can gate admins and hard-lock banned accounts.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared.db import User
from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


class UpsertResult:
    """Lightweight return container for `upsert_user`."""

    __slots__ = ("user_id", "role", "token_version")

    def __init__(self, user_id: UUID, role: str, token_version: int) -> None:
        self.user_id = user_id
        self.role = role
        self.token_version = token_version


async def upsert_user(
    session: AsyncSession,
    *,
    email: str,
    name: str | None,
    image: str | None,
) -> UpsertResult:
    """Idempotently insert or update a `users` row keyed by email.

    Returns the row's UUID plus the current `role` and `token_version` so the
    edge JWT claim is correct on first login (no stale-until-relogin gap).
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
            ).returning(User.id, User.role, User.token_version)
        )
    ).one()
    await session.commit()
    role = row[1].value if hasattr(row[1], "value") else str(row[1])
    return UpsertResult(user_id=row[0], role=role, token_version=int(row[2]))


async def get_with_token_version_check(
    session: AsyncSession,
    *,
    user_id: UUID,
    token_version: int,
) -> dict | None:
    """Return user fields if id exists and `token_version` matches.

    Returns None if user is gone or token_version mismatches. The returned
    dict carries `role` + `banned_at` so the auth layer can gate admins and
    hard-lock banned accounts.
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
    role = row.role.value if hasattr(row.role, "value") else str(row.role)
    return {
        "id": row.id,
        "email": row.email,
        "name": row.name,
        "image": row.image,
        "role": role,
        "banned_at": row.banned_at,
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
    return int(row[0])


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


# ── Admin user-management helpers ─────────────────────────────────
#
# Ban/unban mutators DO NOT commit — the route owns the transaction so the
# `admin_actions` audit row lands in the same unit of work (red-team F7).


async def set_ban(
    session: AsyncSession, *, user_id: UUID, reason: str | None
) -> bool:
    """Set `banned_at=now`, `ban_reason`, bump `token_version`. No commit.

    Returns False if the user does not exist (or is already soft-deleted).
    """
    result = await session.exec(
        update(User)
        .where(User.id == user_id, User.deleted_at.is_(None))
        .values(
            banned_at=func.now(),
            ban_reason=reason,
            token_version=User.token_version + 1,
            updated_at=func.now(),
        )
    )
    return bool(getattr(result, "rowcount", 0))


async def clear_ban(session: AsyncSession, *, user_id: UUID) -> bool:
    """Null `banned_at`/`ban_reason`. No commit, no token_version change.

    Unban does NOT reset token_version: the bump done at ban time is a
    one-way "kill active sessions" signal. A fresh login mints a cookie with
    the current token_version, so the user is never permanently locked out.
    """
    result = await session.exec(
        update(User)
        .where(User.id == user_id)
        .values(banned_at=None, ban_reason=None, updated_at=func.now())
    )
    return bool(getattr(result, "rowcount", 0))


async def bump_token_version(session: AsyncSession, *, user_id: UUID) -> int:
    """Increment token_version WITHOUT committing (caller owns txn).

    Distinct from `revoke_tokens`, which self-commits for the internal-secret
    route. Returns the new version; raises LookupError if the user is gone.
    """
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
    return int(row[0])


async def get_role(session: AsyncSession, *, user_id: UUID) -> str | None:
    """Return the user's role string, or None if the user doesn't exist."""
    row = (
        await session.exec(select(User.role).where(User.id == user_id))
    ).first()
    if row is None:
        return None
    return row.value if hasattr(row, "value") else str(row)


async def count_active_admins(session: AsyncSession) -> int:
    """Count non-deleted, non-banned admins (last-admin guard)."""
    return int(
        (
            await session.exec(
                select(func.count())
                .select_from(User)
                .where(
                    User.role == "admin",
                    User.deleted_at.is_(None),
                    User.banned_at.is_(None),
                )
            )
        ).one()
    )


async def get_me_profile(session: AsyncSession, user) -> dict:
    """Canonical /me payload: identity fields + gamification layered in."""
    row = (
        await session.exec(
            select(
                User.image_url,
                User.streak_days,
                User.xp_total,
                User.level,
                User.badges,
                User.league_rank,
                User.locale,
                User.bio,
            ).where(User.id == user.id)
        )
    ).first()
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "image": user.image,
        "image_url": row.image_url if row else None,
        "streak_days": int(row.streak_days) if row else 0,
        "xp_total": int(row.xp_total) if row else 0,
        "level": int(row.level) if row else 1,
        "badges": (row.badges if row else []) or [],
        "league_rank": int(row.league_rank) if row else 0,
        "locale": (row.locale if row else "en") or "en",
        "bio": row.bio if row else None,
    }
