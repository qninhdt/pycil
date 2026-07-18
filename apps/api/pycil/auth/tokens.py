"""JWT sign/verify — the ONLY module allowed to call jwt.encode/decode.

Every decode pins ``algorithms=["HS256"]`` and requires the core claims, so
alg-confusion and ``alg:none`` tokens are rejected. Access tokens embed ``tv``
(token_version) for per-user revocation; the previous secret is accepted during
rotation only.
"""

import time
import uuid

import jwt

from pycil.auth.models import User
from pycil.config import settings

_ALGO = "HS256"
_REQUIRED_CLAIMS = ["sub", "tv", "exp", "iat"]
_CLOCK_SKEW_SECONDS = 30


def sign_access(user: User) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds) for a user."""
    now = int(time.time())
    ttl = settings.jwt_max_age_seconds
    claims = {
        "sub": str(user.id),
        "tv": user.token_version,
        "iat": now,
        "exp": now + ttl,
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=_ALGO)
    return token, ttl


def verify(token: str) -> dict:
    """Decode + validate a JWT. Raises jwt.PyJWTError on any failure.

    Pins the algorithm and required claims. Tries the current secret, then the
    previous secret (rotation overlap) — never widens the accepted algorithm.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGO],
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError:
        raise
    except jwt.PyJWTError:
        if not settings.jwt_secret_previous:
            raise
        claims = jwt.decode(
            token,
            settings.jwt_secret_previous,
            algorithms=[_ALGO],
            options={"require": _REQUIRED_CLAIMS},
        )

    iat = int(claims["iat"])
    now = int(time.time())
    if iat > now + _CLOCK_SKEW_SECONDS:
        raise jwt.InvalidIssuedAtError("iat_in_future")
    return claims


def new_state_token() -> str:
    """Opaque single-use OAuth state/verifier id (stored in Redis)."""
    return uuid.uuid4().hex
