"""Google OAuth 2.1 with PKCE.

Authorization-code flow only (no implicit grant). The PKCE verifier + state are
stored under a single-use, short-TTL Redis key so a replayed ``state`` cannot
complete a second exchange. Redirect URI is an exact match (no wildcards).
"""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx

from pycil.config import settings
from pycil.db.redis import get_redis

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_STATE_TTL_SECONDS = 600
_SCOPE = "openid email profile"


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


async def build_authorize_url(redirect_uri: str) -> str:
    """Create a state + PKCE challenge, persist verifier in Redis, return the URL."""
    allowed = settings.allowed_oauth_redirect_uris
    if allowed and redirect_uri not in allowed:
        raise ValueError("redirect_uri_not_allowed")
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    redis = get_redis()
    # Single-use key: verifier + the exact redirect_uri it was minted for.
    await redis.hset(f"oauth:state:{state}", mapping={"v": verifier, "r": redirect_uri})
    await redis.expire(f"oauth:state:{state}", _STATE_TTL_SECONDS)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str, state: str) -> dict:
    """Validate single-use state, exchange code+verifier, return Google userinfo.

    Raises ValueError on invalid/expired/replayed state.
    """
    redis = get_redis()
    key = f"oauth:state:{state}"
    data = await redis.hgetall(key)
    # Single-use: delete immediately so a replayed state cannot exchange twice.
    await redis.delete(key)
    if not data:
        raise ValueError("invalid_or_expired_state")
    verifier = data["v"]
    redirect_uri = data["r"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "code_verifier": verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        userinfo_resp = await client.get(
            _USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        userinfo_resp.raise_for_status()
        return userinfo_resp.json()
