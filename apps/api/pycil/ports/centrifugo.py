"""Centrifugo client: sign SSE connection tokens and perform control calls."""

import time
from uuid import UUID

import httpx
import jwt

from pycil.config import settings

_ALGO = "HS256"
_TOKEN_TTL = 900


async def readiness() -> bool:
    """Check the mandatory Centrifugo process without publishing an event."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"{settings.centrifugo_url}/health")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def sign_subscription_token(user_id: UUID | str, token_version: int = 0) -> str:
    """Sign an SSE connection token bound to the current auth token version."""
    return mint_connection_token(user_id, token_version)[0]


def mint_connection_token(user_id: UUID | str, token_version: int) -> tuple[str, int]:
    """Return a connection token together with its exact Unix expiry timestamp."""
    now = int(time.time())
    expires_at = now + _TOKEN_TTL
    claims = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
        # The subscribe proxy revalidates this against Postgres before every
        # subscription, so a revoked access token cannot add new resources.
        "meta": {"tokenVersion": token_version, "expiresAt": expires_at},
    }
    return jwt.encode(claims, settings.centrifugo_token_hmac_secret, algorithm=_ALGO), expires_at


async def disconnect_user(user_id: UUID | str) -> bool:
    """Close every Centrifugo connection belonging to a user.

    Centrifugo can return command-level errors in a successful HTTP response, so
    both transport and API-level failures are treated as an unsuccessful disconnect.
    Callers may safely continue their local logout/revocation flow when this fails.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.post(
                f"{settings.centrifugo_url}/api/disconnect",
                json={"user": str(user_id)},
                headers={"X-API-Key": settings.centrifugo_api_key},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return False
    return isinstance(payload, dict) and not payload.get("error")


async def unsubscribe_channel(user_id: UUID | str, channel: str) -> bool:
    """End one user's subscription to one channel immediately.

    ``expire_at`` bounds a subscription, but Centrifugo evaluates it on its own
    clock, so shortening it does not cut a subscription that is already
    established. This does, which is what makes a terminal task or a logout take
    effect now rather than at the next expiry check.

    Verified against Centrifugo v6.8.3: ``POST /api/unsubscribe`` accepts a
    user/channel pair and answers ``{"result": {}}``. Command-level errors arrive
    inside a 200, so both they and transport failures count as unsuccessful.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            response = await http_client.post(
                f"{settings.centrifugo_url}/api/unsubscribe",
                json={"user": str(user_id), "channel": channel},
                headers={"X-API-Key": settings.centrifugo_api_key},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return False
    return isinstance(payload, dict) and not payload.get("error")
