"""Realtime routes: mint authenticated Centrifugo SSE connection tokens."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import error_responses
from pycil.config import settings
from pycil.db.session import get_session
from pycil.ports.centrifugo import RealtimeControl, get_centrifugo
from pycil.realtime.application.subscriptions import SubscribeProxyRequest, authorize_subscription

router = APIRouter(prefix="/realtime", tags=["realtime"])
subscribe_proxy_router = APIRouter(prefix="/internal/realtime", include_in_schema=False)


async def _current_token_version(session: AsyncSession, user_id: UUID) -> int | None:
    """Read a user's live token version, or None when the user is gone.

    Lives here rather than in `subscriptions`, which is what removes the
    `auth <-> realtime` import cycle: this router already depends on `auth`, so
    the one integer the authorizer needs is supplied from the side that has it.
    """
    return await session.scalar(select(User.token_version).where(User.id == user_id))


class TokenResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str
    expires_at: int = Field(alias="expiresAt")
    sse_url: str = Field(alias="sseUrl")


@router.get("/token", response_model=TokenResponse, responses=error_responses(401, 429))
async def realtime_token(
    user: Annotated[CurrentUser, Depends(current_user)],
    realtime: RealtimeControl = Depends(get_centrifugo),
) -> TokenResponse:
    token, expires_at = realtime.mint_connection_token(user.id, user.token_version)
    return TokenResponse(
        token=token,
        expires_at=expires_at,
        sse_url=settings.centrifugo_public_sse_url,
    )


@subscribe_proxy_router.post("/subscribe")
async def subscribe_proxy(
    body: SubscribeProxyRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Authorize one opaque async resource and return its current snapshot."""
    return await authorize_subscription(session, body, _current_token_version)
