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


# There is deliberately no `unsubscribe_channel` here.
#
# It existed, worked (verified against Centrifugo v6.8.3), and had no caller. The
# terminal-task path closes a subscription window with a clamped `expire_at`
# instead, because unsubscribing at the transition would cut the connection before
# the outbox has published the terminal snapshot — `transition_task` only enqueues
# an outbox row, and the cron relay publishes it up to a minute later.
#
# Kept as a note rather than as code because the reasoning is what a future reader
# needs; the function was a standing invitation to reintroduce that race.
