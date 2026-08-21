"""Realtime routes: mint authenticated Centrifugo SSE connection tokens."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth.deps import current_user, read_token_version
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import error_responses
from pycil.config import settings
from pycil.db.session import get_session
from pycil.ports.centrifugo import RealtimeControl, get_centrifugo
from pycil.realtime.application.subscriptions import SubscribeProxyRequest, authorize_subscription

router = APIRouter(prefix="/realtime", tags=["realtime"])
subscribe_proxy_router = APIRouter(prefix="/internal/realtime", include_in_schema=False)


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
    return await authorize_subscription(session, body, read_token_version)
