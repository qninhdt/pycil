"""JWT-based session validation.

Single source of truth for decoding/validating the `pycil-session` cookie
issued by Next.js Auth.js (HS256 JWS, NOT JWE — see phase-02 plan step 8).

All decode paths funnel through `decode_session`. A lint rule forbids
`jwt.decode` calls outside this module.

`get_current_user` re-reads the `users` row on every request and verifies
the JWT `tv` claim against `users.token_version` for lightweight per-user
revocation. It also hard-locks out banned users (403 `account_banned`) — the
authoritative ban gate is this per-request DB read, not the JWT.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.config import get_settings
from pycil_core.db import get_session
from pycil_core.services import user_service


class CurrentUser(BaseModel):
    id: UUID
    email: str
    name: str | None = None
    image: str | None = None
    role: str = "user"
    banned_at: datetime | None = None


_REQUIRED_CLAIMS = ["exp", "iat", "sub", "tv"]
_CLOCK_SKEW_SECONDS = 30


def decode_session(token: str) -> dict:
    """Decode a JWT cookie. Tries current secret first, then previous (rotation)."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.auth_jwt_secret_current,
            algorithms=["HS256"],
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError:
        raise
    except jwt.PyJWTError:
        if not settings.auth_jwt_secret_previous:
            raise
        claims = jwt.decode(
            token,
            settings.auth_jwt_secret_previous,
            algorithms=["HS256"],
            options={"require": _REQUIRED_CLAIMS},
        )

    iat = int(claims["iat"])
    now = int(time.time())
    if iat > now + _CLOCK_SKEW_SECONDS:
        raise jwt.InvalidIssuedAtError("iat_in_future")
    if now - iat > settings.jwt_max_age_seconds:
        raise jwt.ExpiredSignatureError("token_too_old")
    return claims


async def get_current_user(
    pycil_session: Annotated[
        str | None, Cookie(alias=get_settings().session_cookie_name)
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Validate JWT cookie and re-read the user row. 401 on any failure."""
    if not pycil_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_session")

    try:
        claims = decode_session(pycil_session)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "expired_session") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_session") from exc

    try:
        user_id = UUID(str(claims["sub"]))
        token_version = int(claims["tv"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_session_claims") from exc

    user = await user_service.get_with_token_version_check(
        session, user_id=user_id, token_version=token_version
    )
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session_revoked")
    if user.get("banned_at") is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account_banned")
    return CurrentUser(**user)
