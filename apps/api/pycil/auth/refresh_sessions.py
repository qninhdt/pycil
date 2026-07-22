"""Opaque rotating refresh-token persistence and replay containment."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.models import RefreshSession, User
from pycil.config import settings


def _now() -> datetime:
    return datetime.now(UTC)


def refresh_ttl_seconds() -> int:
    return int(getattr(settings, "refresh_token_ttl_seconds", 60 * 60 * 24 * 30))


def _digest(token: str) -> str:
    pepper = getattr(settings, "refresh_token_pepper", "")
    if not pepper:
        raise RuntimeError("refresh_token_pepper is not configured")
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(48)


async def issue(
    session: AsyncSession, user_id: UUID, family_id: UUID | None = None
) -> tuple[str, int]:
    """Issue one opaque token. The raw credential never reaches persistence."""
    raw = _new_token()
    ttl = refresh_ttl_seconds()
    session.add(
        RefreshSession(
            user_id=user_id,
            family_id=family_id or uuid4(),
            token_digest=_digest(raw),
            expires_at=_now() + timedelta(seconds=ttl),
        )
    )
    return raw, ttl


async def revoke_user_sessions(
    session: AsyncSession, user_id: UUID, *, bump_version: bool = True
) -> None:
    now = _now()
    await session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if bump_version:
        await session.execute(
            update(User).where(User.id == user_id).values(token_version=User.token_version + 1)
        )


async def rotate(session: AsyncSession, raw_token: str) -> tuple[User, str, int] | None:
    """Consume exactly once and create its successor in the same transaction.

    A known, no-longer-active token is a replay: contain it by revoking every
    refresh family for its user and invalidating outstanding access JWTs.
    """
    digest = _digest(raw_token)
    row = (
        await session.execute(
            select(RefreshSession).where(RefreshSession.token_digest == digest).with_for_update()
        )
    ).scalars().first()
    if row is None:
        return None

    now = _now()
    if row.revoked_at is not None or row.expires_at <= now:
        await revoke_user_sessions(session, row.user_id)
        await session.commit()
        return None

    user = await session.get(User, row.user_id, with_for_update=True)
    if user is None:  # Defensive; FK normally makes this unreachable.
        row.revoked_at = now
        await session.commit()
        return None
    raw_next, ttl = await issue(session, user.id, row.family_id)
    await session.flush()
    successor = (
        await session.execute(
            select(RefreshSession).where(RefreshSession.token_digest == _digest(raw_next))
        )
    ).scalars().one()
    # Row-level lock + one transaction make concurrent attempts serialize.
    row.revoked_at = now
    row.replaced_by_id = successor.id
    await session.commit()
    await session.refresh(user)
    return user, raw_next, ttl
