"""A local Clerk stand-in: real RSA signing, a real JWKS endpoint, no mocking.

Tests that need an authenticated caller mint a token here instead of reaching into
the verification path. Because the token is signed by a genuine RSA key and the
public half is fetched over HTTP from this stub, the algorithm pinning,
issuer/audience/expiry validation and key rotation all execute as they do in
production — a test cannot pass by bypassing verification.

This replaces the removed `pycil.auth.tokens.sign_access` helper: Pycil no longer
mints credentials, so tests no longer can either.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pycil.account import auth as deps
from pycil.platform.settings import settings

ISSUER = "https://clerk.test.invalid"
AUDIENCE = "pycil-test"


def _b64url(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class ClerkStub:
    """Serves a JWKS document and signs tokens against the matching private key."""

    def __init__(self) -> None:
        self._keys: dict[str, rsa.RSAPrivateKey] = {}
        self.kid = "key-1"
        self._add_key(self.kid)
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None
        self.url = ""

    def _add_key(self, kid: str) -> None:
        self._keys[kid] = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @property
    def private_key(self) -> rsa.RSAPrivateKey:
        return self._keys[self.kid]

    def rotate(self, kid: str) -> None:
        """Publish a new key and make it the signing key, as Clerk's rotation does."""
        self._add_key(kid)
        self.kid = kid

    def document(self) -> dict:
        keys = []
        for kid, key in self._keys.items():
            numbers = key.public_key().public_numbers()
            keys.append(
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": kid,
                    "n": _b64url(numbers.n),
                    "e": _b64url(numbers.e),
                }
            )
        return {"keys": keys}

    def start(self) -> str:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib handler signature
                body = json.dumps(stub.document()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # noqa: D102 - silence the stub's access log
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"
        self.url = f"{self.base_url}/jwks"
        return self.url

    @property
    def public_key_pem(self) -> str:
        from cryptography.hazmat.primitives import serialization

        return (
            self.private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def token(
        self,
        *,
        subject: str,
        email: str | None = None,
        email_verified: bool = True,
        expires_in: int = 300,
        issuer: str = ISSUER,
        audience: str = AUDIENCE,
    ) -> str:
        """A token shaped like one Clerk issues.

        ``email_verified`` defaults to true because that is what Clerk emits for a
        verified address, and only a verified claim may link an existing account.
        Pass ``email_verified=False`` to exercise the unverified path, which must
        provision a new account rather than claim someone else's.
        """
        now = int(time.time())
        claims = {
            "sub": subject,
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "exp": now + expires_in,
        }
        if email is not None:
            claims["email"] = email
            claims["email_verified"] = email_verified
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.kid})


@pytest.fixture(scope="session")
def clerk_stub() -> Iterator[ClerkStub]:
    """One stub per session: key generation is the slow part."""
    stub = ClerkStub()
    stub.start()
    yield stub
    stub.stop()


@pytest.fixture(autouse=True)
def configure_clerk(clerk_stub, monkeypatch):
    """Point the verifier at the stub and drop any cached JWKS client.

    Autouse so every test in a module that requests `clerk_stub` gets a verifier
    that trusts it, without each test remembering to wire it up.
    """
    monkeypatch.setattr(settings, "clerk_jwks_url", clerk_stub.url)
    monkeypatch.setattr(settings, "clerk_issuer", ISSUER)
    monkeypatch.setattr(settings, "clerk_audience", AUDIENCE)
    monkeypatch.setattr(deps, "_jwks_client", None)
    yield
    deps._jwks_client = None


def bearer(token: str) -> dict[str, str]:
    """The header a client would send for this token."""
    return {"Authorization": f"Bearer {token}"}
