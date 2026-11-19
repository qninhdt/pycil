from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pycil.infrastructure.clerk import Identity, InvalidIdentityError


async def test_identity_accepts_token_with_reasonable_clock_drift(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = Identity("https://identity.invalid/jwks", "https://identity.invalid", "pycil")
    monkeypatch.setattr(
        identity.keys,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=private_key.public_key()),
    )
    now = datetime.now(UTC)
    claims = {
        "sub": "user_drifted",
        "iss": "https://identity.invalid",
        "aud": "pycil",
        "iat": now + timedelta(seconds=15),
        "nbf": now + timedelta(seconds=15),
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    subject = await identity.subject(token)
    assert subject == "user_drifted"


async def test_identity_rejects_token_with_excessive_clock_drift(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = Identity("https://identity.invalid/jwks", "https://identity.invalid", "pycil")
    monkeypatch.setattr(
        identity.keys,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=private_key.public_key()),
    )
    now = datetime.now(UTC)
    claims = {
        "sub": "user_excessive",
        "iss": "https://identity.invalid",
        "aud": "pycil",
        "iat": now + timedelta(seconds=120),
        "nbf": now + timedelta(seconds=120),
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    with pytest.raises(InvalidIdentityError):
        await identity.subject(token)
