"""Realtime routes: mint authenticated Centrifugo connection tokens.

Subscriptions use Centrifugo v5's user-limited channel boundary (``#user_id``)
instead of a subscription JWT: v5 treats a valid channel JWT as an independent
capability, so it does not bind that JWT's subject to the connection user.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import error_responses
from pycil.config import settings
from pycil.realtime import client

router = APIRouter(prefix="/realtime", tags=["realtime"])


class TokenResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str
    expires_at: int = Field(alias="expiresAt")
    websocket_url: str = Field(alias="websocketUrl")


@router.get("/token", response_model=TokenResponse, responses=error_responses(401, 429))
async def realtime_token(
    user: Annotated[CurrentUser, Depends(current_user)],
) -> TokenResponse:
    token, expires_at = client.mint_connection_token(user.id)
    return TokenResponse(
        token=token,
        expires_at=expires_at,
        websocket_url=settings.centrifugo_public_websocket_url,
    )
