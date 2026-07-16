"""Realtime routes: mint authenticated Centrifugo connection tokens.

Subscriptions use Centrifugo v5's user-limited channel boundary (``#user_id``)
instead of a subscription JWT: v5 treats a valid channel JWT as an independent
capability, so it does not bind that JWT's subject to the connection user.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from pycil.auth.deps import current_user
from pycil.auth.schemas import CurrentUser
from pycil.realtime import client

router = APIRouter(prefix="/realtime", tags=["realtime"])


class TokenResponse(BaseModel):
    token: str


@router.get("/token", response_model=TokenResponse)
async def realtime_token(
    user: Annotated[CurrentUser, Depends(current_user)],
) -> TokenResponse:
    return TokenResponse(token=client.sign_subscription_token(user.id))
