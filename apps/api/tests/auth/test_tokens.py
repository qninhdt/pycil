"""Token sign/verify security: alg-pinning, required claims, tv, expiry."""

import time
import uuid

import jwt
import pytest

from pycil.auth import tokens
from pycil.auth.models import User
from pycil.config import settings


def _user(tv: int = 0) -> User:
    return User(id=uuid.uuid4(), email="a@b.co", token_version=tv)


def test_sign_and_verify_roundtrip():
    user = _user(tv=3)
    token, ttl = tokens.sign_access(user)
    claims = tokens.verify(token)
    assert claims["sub"] == str(user.id)
    assert claims["tv"] == 3
    assert ttl == settings.jwt_max_age_seconds


def test_verify_rejects_alg_none():
    user = _user()
    # Forge an unsigned alg:none token with all required claims.
    now = int(time.time())
    forged = jwt.encode(
        {"sub": str(user.id), "tv": 0, "iat": now, "exp": now + 999},
        key="",
        algorithm="none",
    )
    with pytest.raises(jwt.PyJWTError):
        tokens.verify(forged)


def test_verify_rejects_wrong_secret():
    now = int(time.time())
    forged = jwt.encode(
        {"sub": "x", "tv": 0, "iat": now, "exp": now + 999},
        key="attacker-secret",
        algorithm="HS256",
    )
    with pytest.raises(jwt.PyJWTError):
        tokens.verify(forged)


def test_verify_requires_core_claims():
    now = int(time.time())
    # Missing token version.
    incomplete = jwt.encode(
        {"sub": "x", "iat": now, "exp": now + 999},
        key=settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        tokens.verify(incomplete)


def test_verify_rejects_expired():
    now = int(time.time())
    expired = jwt.encode(
        {"sub": "x", "tv": 0, "iat": now - 10, "exp": now - 1},
        key=settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        tokens.verify(expired)


def test_verify_rejects_future_iat():
    now = int(time.time())
    future = jwt.encode(
        {"sub": "x", "tv": 0, "iat": now + 3600, "exp": now + 7200},
        key=settings.jwt_secret,
        algorithm="HS256",
    )
    # Rejected either by PyJWT's ImmatureSignatureError or our future-iat guard;
    # both are PyJWTError subclasses.
    with pytest.raises(jwt.PyJWTError):
        tokens.verify(future)
