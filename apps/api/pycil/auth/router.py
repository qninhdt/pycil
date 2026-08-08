"""Auth routes: OAuth login/callback + refresh + logout.

The API is bearer-only: /auth/callback returns the signed JWT for the frontend
to seal into its iron-session. No server-side session is created here.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth import oauth, refresh_sessions, tokens
from pycil.auth.deps import get_user_by_email, optional_current_user
from pycil.auth.models import RefreshSession, User
from pycil.auth.schemas import CurrentUser, LoginStart, LogoutRequest, RefreshRequest, TokenResponse
from pycil.common.errors import AppError, UnauthorizedError
from pycil.db.session import get_session
from pycil.ports.centrifugo import RealtimeControl, get_centrifugo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login", response_model=LoginStart)
async def login(redirect_uri: Annotated[str, Query()]) -> LoginStart:
    try:
        url = await oauth.build_authorize_url(redirect_uri)
    except ValueError as exc:
        raise AppError("invalid_redirect_uri", code="invalid_redirect_uri") from exc
    return LoginStart(authorize_url=url)


@router.get("/callback", response_model=TokenResponse)
async def callback(
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        userinfo = await oauth.exchange_code(code, state)
    except Exception as exc:
        # The diagnosis belongs in the log, not on the wire: the provider's message
        # can carry internal hostnames, URLs or token fragments.
        logger.error("OAuth exchange_code failed", exc_info=True)
        raise UnauthorizedError("oauth_exchange_failed") from exc

    email = userinfo.get("email")
    if not email or userinfo.get("email_verified") is not True:
        # Deliberately not the whole payload: `userinfo` carries the name and photo
        # URL as well, and an unverified email is an expected outcome rather than an
        # incident that justifies putting third-party personal data in the logs.
        logger.warning(
            "OAuth rejected: email missing or unverified",
            extra={"email_present": bool(email), "email_verified": userinfo.get("email_verified")},
        )
        raise UnauthorizedError("oauth_email_not_verified")

    # Upsert user in the same transaction, then issue the JWT.
    user = await get_user_by_email(session, email)
    if user is None:
        user = User(email=email, name=userinfo.get("name"), image=userinfo.get("picture"))
        session.add(user)
    else:
        user.name = userinfo.get("name") or user.name
        user.image = userinfo.get("picture") or user.image
    await session.commit()
    await session.refresh(user)

    token, ttl = tokens.sign_access(user)
    refresh_token, refresh_ttl = await refresh_sessions.issue(session, user.id)
    await session.commit()
    return TokenResponse(
        access_token=token,
        refresh_token=refresh_token,
        expires_in=ttl,
        refresh_expires_in=refresh_ttl,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest | None = None,
    user: CurrentUser | None = Depends(optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    if body is not None:
        result = await refresh_sessions.rotate(session, body.refresh_token)
        if result is None:
            raise UnauthorizedError("invalid_refresh_token")
        user, refresh_token, refresh_ttl = result
    elif user is not None:
        # v1 compatibility: old BFFs used a bearer-only refresh. Issue their
        # first rotating token and return it alongside the renewed access JWT.
        refresh_token, refresh_ttl = await refresh_sessions.issue(session, user.id)
        await session.commit()
    else:
        raise UnauthorizedError("missing_refresh_token")
    token, ttl = tokens.sign_access(user)
    return TokenResponse(
        access_token=token,
        refresh_token=refresh_token,
        expires_in=ttl,
        refresh_expires_in=refresh_ttl,
    )


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutRequest | None = None,
    user: CurrentUser | None = Depends(optional_current_user),
    session: AsyncSession = Depends(get_session),
    realtime: RealtimeControl = Depends(get_centrifugo),
) -> None:
    # Idempotent even for a token already rotated, expired, or unknown.
    user_id = user.id if user is not None else None
    if body is not None:
        digest = refresh_sessions.token_digest(body.refresh_token)
        row = (
            await session.execute(
                select(RefreshSession)
                .where(RefreshSession.token_digest == digest)
                .with_for_update()
            )
        ).scalars().first()
        user_id = row.user_id if row is not None else user_id
    if user_id is not None:
        await refresh_sessions.revoke_user_sessions(session, user_id)
        await session.commit()
        # Revocation is authoritative; closing sockets shortens the exposure
        # window for an already connected realtime client. Best-effort by design —
        # logout must still succeed — but a failure is logged rather than dropped,
        # because it is the only signal that sockets outlived a revocation. The
        # connection token has no revocation list, so that window is up to 900s.
        if not await realtime.disconnect_user(user_id):
            logger.warning(
                "realtime disconnect failed after logout; sockets may outlive revocation",
                extra={"user_id": str(user_id)},
            )
