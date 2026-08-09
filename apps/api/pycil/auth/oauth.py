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
import jwt

from pycil.config import settings
from pycil.db.redis import get_redis

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
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
    nonce = secrets.token_urlsafe(24)
    # Single-use key: verifier, nonce, and the exact redirect URI it was minted for.
    await redis.hset(
        f"oauth:state:{state}", mapping={"v": verifier, "r": redirect_uri, "n": nonce}
    )
    await redis.expire(f"oauth:state:{state}", _STATE_TTL_SECONDS)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "nonce": nonce,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str, state: str) -> dict:
    """Validate state, exchange code, and validate the OIDC ID token.

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
    nonce = data.get("n")
    if not nonce:
        raise ValueError("oauth_nonce_missing")

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
        id_token = token_resp.json().get("id_token")
        if not id_token:
            raise ValueError("oauth_id_token_missing")
        jwks_response = await client.get(_JWKS_URL)
        jwks_response.raise_for_status()
    return _validate_id_token(id_token, jwks_response.json(), nonce)


def _validate_id_token(id_token: str, jwks: dict, nonce: str) -> dict:
    """Verify signature, issuer, audience, expiry, and nonce before trusting claims."""
    try:
        header = jwt.get_unverified_header(id_token)
        key_id = header.get("kid")
        if header.get("alg") != "RS256" or not key_id:
            raise ValueError("invalid_id_token_header")
        keys = jwt.PyJWKSet.from_dict(jwks).keys
        jwk = next((candidate for candidate in keys if candidate.key_id == key_id), None)
        if jwk is None:
            raise ValueError("id_token_key_not_found")
        claims = jwt.decode(
            id_token,
            jwk.key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            options={"require": ["sub", "aud", "exp", "iat", "nonce"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError("invalid_id_token") from exc
    if claims.get("iss") not in _ISSUERS:
        raise ValueError("invalid_id_token_issuer")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ValueError("invalid_id_token_nonce")
    return claims
