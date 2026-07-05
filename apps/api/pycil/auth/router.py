"""Auth routes: OAuth login/callback + refresh + logout.

The API is bearer-only: /auth/callback returns the signed JWT for the frontend
to seal into its iron-session. No server-side session is created here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth import oauth, tokens
from pycil.auth.deps import current_user, get_user_by_email
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser, LoginStart, TokenResponse
from pycil.common.errors import UnauthorizedError
from pycil.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login", response_model=LoginStart)
async def login(redirect_uri: Annotated[str, Query()]) -> LoginStart:
    url = await oauth.build_authorize_url(redirect_uri)
    return LoginStart(authorize_url=url)


@router.get("/callback", response_model=TokenResponse)
async def callback(
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        userinfo = await oauth.exchange_code(code, state)
    except ValueError as exc:
        raise UnauthorizedError("invalid_oauth_state") from exc

    email = userinfo.get("email")
    if not email:
        raise UnauthorizedError("oauth_no_email")

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
    return TokenResponse(access_token=token, expires_in=ttl)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    # Reissue against current token_version — no server session to rotate.
    db_user = await session.get(User, user.id)
    token, ttl = tokens.sign_access(db_user)
    return TokenResponse(access_token=token, expires_in=ttl)


@router.post("/logout", status_code=204)
async def logout(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: AsyncSession = Depends(get_session),
) -> None:
    # Bump token_version → all previously issued JWTs fail the tv re-read.
    db_user = await session.get(User, user.id)
    db_user.token_version += 1
    await session.commit()
