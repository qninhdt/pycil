"""Auth dependencies: bearer-only current_user + require_admin.

The API reads the JWT from the ``Authorization: Bearer`` header ONLY — never a
cookie — so CSRF is out of scope by design. ``role``, ``token_version`` and
``banned_at`` are re-read from the DB on every request; the JWT claims are
edge-convenience only. A ``token_version`` mismatch or a non-null ``banned_at``
rejects the request.
"""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from pycil.auth import tokens
from pycil.auth.models import User, UserRole
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import ForbiddenError, UnauthorizedError
from pycil.db.session import get_session

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise UnauthorizedError("missing_token")

    try:
        claims = tokens.verify(creds.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("expired_token", code="expired_token") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("invalid_token") from exc

    try:
        user_id = UUID(str(claims["sub"]))
        claim_tv = int(claims["tv"])
    except (KeyError, ValueError, TypeError) as exc:
        raise UnauthorizedError("invalid_token_claims") from exc

    user = await session.get(User, user_id)
    # Re-read authoritative state — JWT claims are edge-convenience only.
    if user is None or user.token_version != claim_tv:
        raise UnauthorizedError("token_revoked")
    if user.banned_at is not None:
        raise ForbiddenError("account_banned", code="account_banned")

    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        image=user.image,
        role=user.role,
        banned_at=user.banned_at,
    )


async def require_admin(
    user: Annotated[CurrentUser, Depends(current_user)],
) -> CurrentUser:
    if user.role != UserRole.admin:
        raise ForbiddenError("admin_required", code="admin_required")
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalars().first()
