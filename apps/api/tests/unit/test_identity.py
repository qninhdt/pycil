from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pycil.account.auth import Identity
from pycil.http import Problem


@pytest.fixture
def signed_identity(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = Identity(
        SimpleNamespace(
            clerk_jwks_url="https://example.invalid/jwks",
            clerk_issuer="https://issuer.example.invalid",
            clerk_audience="pycil",
        )
    )
    monkeypatch.setattr(
        identity.keys,
        "get_signing_key_from_jwt",
        lambda token: SimpleNamespace(key=private.public_key()),
    )
    return identity, private


def claims():
    return {
        "sub": "user_secure",
        "iss": "https://issuer.example.invalid",
        "aud": "pycil",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }


async def test_clerk_subject_requires_actual_signature_and_claims(signed_identity):
    identity, key = signed_identity
    token = jwt.encode(claims(), key, algorithm="RS256")
    assert await identity.subject(token) == "user_secure"
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(Problem, match="invalid_credentials"):
        await identity.subject(jwt.encode(claims(), other, algorithm="RS256"))


@pytest.mark.parametrize(
    "change",
    [
        {"iss": "https://attacker.invalid"},
        {"aud": "other"},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"sub": ""},
        {"sub": 12},
    ],
)
async def test_wrong_identity_claims_rejected(signed_identity, change):
    identity, key = signed_identity
    with pytest.raises(Problem, match="invalid_credentials"):
        await identity.subject(jwt.encode(claims() | change, key, algorithm="RS256"))


async def test_missing_subject_cannot_claim_an_account(signed_identity):
    identity, key = signed_identity
    values = claims()
    values.pop("sub")
    with pytest.raises(Problem, match="invalid_credentials"):
        await identity.subject(jwt.encode(values, key, algorithm="RS256"))
