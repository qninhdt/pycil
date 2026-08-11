"""Opaque rotating refresh-token persistence and replay containment."""

import base64
import hashlib
import hmac
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


def replay_grace_seconds() -> int:
    return int(getattr(settings, "refresh_token_replay_grace_seconds", 60))


def _pepper() -> bytes:
    pepper = getattr(settings, "refresh_token_pepper", "")
    if not pepper:
        raise RuntimeError("refresh_token_pepper is not configured")
    return pepper.encode()


def token_digest(token: str) -> str:
    """Peppered digest of a raw refresh token — the form stored and compared.

    Public because two callers outside this module need it to look a session up by
    raw token: the logout route and account deletion's ownership check. Both were
    reaching into `_digest`, whose underscore says this module reserves the right
    to change it.
    """
    return hmac.new(_pepper(), token.encode(), hashlib.sha256).hexdigest()


# Retained as an alias: this module's own call sites read better unprefixed, and
# removing it would be a rename for no gain.
_digest = token_digest


def _token_for_id(session_id: UUID) -> str:
    """Derive an opaque bearer token without persisting its raw value.

    The row UUID supplies 128 random bits and the peppered MAC supplies another
    256 bits. Keeping the token derivable from the successor row lets a retry
    recover after a process dies between the database commit and its HTTP reply.
    """
    payload = session_id.bytes
    proof = hmac.new(_pepper(), b"pycil-refresh:" + payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + proof).rstrip(b"=").decode()


def _new_token() -> tuple[UUID, str]:
    session_id = uuid4()
    return session_id, _token_for_id(session_id)


async def issue(
    session: AsyncSession, user_id: UUID, family_id: UUID | None = None
) -> tuple[str, int]:
    """Issue one opaque token. The raw credential never reaches persistence."""
    session_id, raw = _new_token()
    ttl = refresh_ttl_seconds()
    session.add(
        RefreshSession(
            id=session_id,
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
    """Consume a token and create its successor in the same transaction.

    A recently replaced token recovers its deterministic successor so overlapping
    requests and a retry after a process failure converge. An older replay is
    contained by revoking every refresh family for its user.
    """
    digest = _digest(raw_token)
    row = (
        (
            await session.execute(
                select(RefreshSession)
                .where(RefreshSession.token_digest == digest)
                .with_for_update()
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return None

    now = _now()
    if row.revoked_at is not None:
        grace_deadline = row.revoked_at + timedelta(seconds=replay_grace_seconds())
        if row.replaced_by_id is not None and now < grace_deadline:
            successor = await session.get(RefreshSession, row.replaced_by_id)
            user = await session.get(User, row.user_id)
            if user is not None and successor is not None and successor.revoked_at is None:
                if successor.id is not None and successor.expires_at > now:
                    raw_successor = _token_for_id(successor.id)
                    # Rows issued before deterministic token recovery existed have
                    # no recoverable raw credential. Never fabricate a token whose
                    # digest does not match the persisted successor; such a legacy
                    # replay falls through to family revocation instead.
                    if hmac.compare_digest(_digest(raw_successor), successor.token_digest):
                        remaining = max(1, int((successor.expires_at - now).total_seconds()))
                        return user, raw_successor, remaining

        await revoke_user_sessions(session, row.user_id)
        await session.commit()
        return None

    if row.expires_at <= now:
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
        (
            await session.execute(
                select(RefreshSession).where(RefreshSession.token_digest == _digest(raw_next))
            )
        )
        .scalars()
        .one()
    )
    # Row-level lock + one transaction make concurrent attempts serialize.
    row.revoked_at = now
    row.replaced_by_id = successor.id
    await session.commit()
    return user, raw_next, ttl
