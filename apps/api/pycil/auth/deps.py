"""Auth dependencies: bearer-only current_user.

The API reads the JWT from the ``Authorization: Bearer`` header ONLY — never a
cookie — so CSRF is out of scope by design. ``token_version`` is re-read from
the DB on every request; a mismatch rejects the request.
"""

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from pycil.auth import tokens
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import UnauthorizedError
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
    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        image=user.image,
        token_version=user.token_version,
    )


async def optional_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    session: AsyncSession = Depends(get_session),
) -> CurrentUser | None:
    """Return an authenticated identity when supplied, otherwise stay anonymous.

    Invalid supplied credentials are never silently downgraded to anonymous.
    This is used only by explicitly public read routes.
    """
    if creds is None or not creds.credentials:
        return None
    return await current_user(creds=creds, session=session)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalars().first()
