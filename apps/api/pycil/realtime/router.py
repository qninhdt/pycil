"""Realtime routes: mint a Centrifugo subscription token for the caller.

The token's subject is the authenticated user's id; Centrifugo's namespace config
grants subscribe only to ``users:{sub}:*``, so a caller can never subscribe to
another user's channels.
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
