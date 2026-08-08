"""A substitutable realtime broker for tests.

Replaces the `monkeypatch.setattr(centrifugo.httpx, "AsyncClient", ...)` pattern
that three test sites used. That patch reached *through* the port at a transport
detail: it asserted how the call was made rather than what the caller asked for,
so any change to the HTTP mechanics broke tests about logout and account deletion.

This fake substitutes at the boundary instead. Consumers take `RealtimeControl`
via `Depends`, so a test installs this through `dependency_overrides` and the
adapter — along with `httpx` entirely — is simply absent from the run.

`disconnect_user` returning False is the interesting case, not an edge one: both
callers log a warning and continue, because revocation is already committed in
Postgres and a live socket only shortens how long a stale connection lingers.
"""

import time
from uuid import UUID

import jwt

from pycil.config import settings

_ALGO = "HS256"
_TOKEN_TTL = 900


class FakeRealtimeControl:
    """Records what it was asked to do; answers however the test needs.

    Tokens are signed for real with the configured secret, because a caller that
    decodes one is testing the claim set, not the signing. Everything else is
    recorded so a test can assert the call happened without asserting how.
    """

    def __init__(self, *, reachable: bool = True, disconnects: bool = True) -> None:
        self._reachable = reachable
        self._disconnects = disconnects
        self.disconnected: list[str] = []
        self.minted: list[tuple[str, int]] = []
        self.readiness_calls = 0

    async def readiness(self) -> bool:
        self.readiness_calls += 1
        return self._reachable

    def mint_connection_token(self, user_id: UUID | str, token_version: int) -> tuple[str, int]:
        now = int(time.time())
        expires_at = now + _TOKEN_TTL
        self.minted.append((str(user_id), token_version))
        claims = {
            "sub": str(user_id),
            "iat": now,
            "exp": expires_at,
            "meta": {"tokenVersion": token_version, "expiresAt": expires_at},
        }
        token = jwt.encode(claims, settings.centrifugo_token_hmac_secret, algorithm=_ALGO)
        return token, expires_at

    async def disconnect_user(self, user_id: UUID | str) -> bool:
        self.disconnected.append(str(user_id))
        return self._disconnects
