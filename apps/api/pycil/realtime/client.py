"""Centrifugo client: publish via HTTP API + sign connection tokens.

Channel access is enforced by Centrifugo's user-limited ``#user_id`` boundary,
which is checked against this connection token's subject. Publishing uses the
HTTP API with the API key.
"""

import time
from uuid import UUID

import httpx
import jwt

from pycil.config import settings

_ALGO = "HS256"
_TOKEN_TTL = 3600


async def readiness() -> bool:
    """Check the mandatory Centrifugo process without publishing an event."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.centrifugo_url}/health")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def sign_subscription_token(user_id: UUID | str) -> str:
    """Sign a Centrifugo connection token whose ``sub`` is the user id."""
    now = int(time.time())
    claims = {"sub": str(user_id), "iat": now, "exp": now + _TOKEN_TTL}
    return jwt.encode(claims, settings.centrifugo_token_hmac_secret, algorithm=_ALGO)
async def publish(channel: str, data: dict) -> None:
    """Publish a payload to a Centrifugo channel via its HTTP API.

    Best-effort: a publish failure never breaks the request that triggered it —
    the verdict is already persisted to ``responses`` and recoverable on refetch.
    """
    url = f"{settings.centrifugo_url}/api/publish"
    headers = {"X-API-Key": settings.centrifugo_api_key}
    body = {"channel": channel, "data": data}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPError:
        # Missed push is recoverable (responses table); do not fail the caller.
        return
