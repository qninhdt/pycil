"""The realtime broker as a port: one Protocol, one adapter, one reused client.

This module used to be a handful of module-level functions, each opening its own
`httpx.AsyncClient` and reading the global `settings` directly. Two costs, one
structural and one real:

- Tests substituted the broker by patching `centrifugo.httpx.AsyncClient`, i.e. by
  reaching *through* the seam at a transport detail. Any change to how the HTTP
  call is made broke tests that had nothing to do with HTTP.
- A client per call means no connection reuse and no single place to set a timeout.

`ports/lexi.py` next door was already a real Protocol with fakes and a boundary
test, so `ports/` held two conventions and a reader could not tell from the
directory which kind they were opening. This standardises on the better one.

`mint_connection_token` is deliberately synchronous: it signs a JWT locally and
never touches the network, so making it `async` for symmetry would imply an I/O
cost that does not exist.

There is deliberately no `unsubscribe_channel`.

It existed, worked (verified against Centrifugo v6.8.3), and had no caller. The
terminal-task path closes a subscription window with a clamped `expire_at`
instead, because unsubscribing at the transition would cut the connection before
the outbox has published the terminal snapshot — `transition_task` only enqueues
an outbox row, and the cron relay publishes it up to a minute later.

Kept as a note rather than as code because the reasoning is what a future reader
needs; the function was a standing invitation to reintroduce that race.
"""

import time
from typing import Protocol
from uuid import UUID

import httpx
import jwt

from pycil.config import settings

_ALGO = "HS256"
_TOKEN_TTL = 900

# Health is on the request path of `/health/ready`, so it fails fast; the control
# calls run after a logout or deletion has already been committed and can afford to
# wait a little longer for a definite answer.
_READINESS_TIMEOUT = 2.0
_CONTROL_TIMEOUT = 5.0


class RealtimeControl(Protocol):
    """What pycil needs from the realtime broker. Nothing about HTTP."""

    async def readiness(self) -> bool:
        """Whether the broker is reachable, without publishing anything."""

    def mint_connection_token(self, user_id: UUID | str, token_version: int) -> tuple[str, int]:
        """A connection token and its exact Unix expiry."""

    async def disconnect_user(self, user_id: UUID | str) -> bool:
        """Close every connection belonging to a user. False if that did not land."""


class CentrifugoControl:
    """`RealtimeControl` over Centrifugo's HTTP API.

    One `httpx.AsyncClient` for the process, so connections are reused and the
    timeout is set in exactly one place.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=_CONTROL_TIMEOUT)

    async def readiness(self) -> bool:
        try:
            response = await self._client.get(
                f"{settings.centrifugo_url}/health", timeout=_READINESS_TIMEOUT
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def mint_connection_token(self, user_id: UUID | str, token_version: int) -> tuple[str, int]:
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
        token = jwt.encode(claims, settings.centrifugo_token_hmac_secret, algorithm=_ALGO)
        return token, expires_at

    async def disconnect_user(self, user_id: UUID | str) -> bool:
        """Close every Centrifugo connection belonging to a user.

        Centrifugo can return command-level errors in a successful HTTP response,
        so both transport and API-level failures count as an unsuccessful
        disconnect. Callers may safely continue their local logout/revocation flow
        when this fails.
        """
        try:
            response = await self._client.post(
                f"{settings.centrifugo_url}/api/disconnect",
                json={"user": str(user_id)},
                headers={"X-API-Key": settings.centrifugo_api_key},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return False
        return isinstance(payload, dict) and not payload.get("error")

    async def close(self) -> None:
        await self._client.aclose()


_control: CentrifugoControl | None = None


def get_centrifugo() -> RealtimeControl:
    """The process's broker adapter, built on first use.

    Taken via `Depends` by every consumer, which is what lets a test substitute the
    fake through `dependency_overrides` rather than by patching a transport class.
    """
    global _control
    if _control is None:
        _control = CentrifugoControl()
    return _control


async def close_centrifugo() -> None:
    """Release the shared client at shutdown."""
    global _control
    if _control is not None:
        await _control.close()
    _control = None
