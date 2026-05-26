"""Integration tests: auth path on `/me`.

Auth happy + missing/bad cookie → 401 with no PII leak.
"""
from __future__ import annotations

import time

import jwt
import pytest

from pycil_core.config import get_settings


@pytest.fixture
def signed_cookie():
    """Build a valid JWT cookie for the deterministic test user."""
    def _make(user_id: str, *, expired: bool = False, bad_sig: bool = False) -> str:
        settings = get_settings()
        secret = "wrong-secret" if bad_sig else settings.auth_jwt_secret_current
        now = int(time.time())
        iat = now - settings.jwt_max_age_seconds - 100 if expired else now
        claims = {
            "sub": user_id,
            "tv": 0,
            "iat": iat,
            "exp": iat + settings.jwt_max_age_seconds,
        }
        return jwt.encode(claims, secret, algorithm="HS256")
    return _make


async def test_no_cookie_returns_401(client_real_auth) -> None:
    response = await client_real_auth.get("/me")
    assert response.status_code == 401


async def test_bad_signature_returns_401(client_real_auth, test_user, signed_cookie) -> None:
    cookie = signed_cookie(str(test_user["id"]), bad_sig=True)
    response = await client_real_auth.get(
        "/me",
        cookies={get_settings().session_cookie_name: cookie},
    )
    assert response.status_code == 401
    # Response body must not leak claim contents.
    body = response.text
    assert "sub" not in body
    assert str(test_user["id"]) not in body


async def test_valid_cookie_returns_user(
    client_real_auth, test_user, signed_cookie
) -> None:
    cookie = signed_cookie(str(test_user["id"]))
    response = await client_real_auth.get(
        "/me",
        cookies={get_settings().session_cookie_name: cookie},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(test_user["id"])
    assert body["email"] == test_user["email"]
