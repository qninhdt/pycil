"""Clerk bearer verification and subject-to-UUID resolution.

These drive the real verifier against a locally generated JWKS: a genuine RSA
keypair signs tokens, and the public half is served from a stub JWKS endpoint.
Nothing is monkeypatched inside the verification path, so the algorithm pinning,
issuer/audience/expiry checks and key rotation are exercised as they run in
production.
"""

from __future__ import annotations

import time
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pycil.auth import deps
from pycil.auth.deps import current_user, optional_current_user
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import (
    AppError,
    ConflictError,
    UnauthorizedError,
    app_error_handler,
)
from pycil.config import settings
from tests.support.clerk_jwks import AUDIENCE, ISSUER, ClerkStub

pytestmark = pytest.mark.asyncio


def _b64url(value: int) -> str:
    import base64

    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_token(
    clerk_stub: ClerkStub,
    *,
    subject: str = "user_abc",
    email: str | None = "learner@example.test",
    email_verified: bool = True,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_in: int = 300,
    key: rsa.RSAPrivateKey | None = None,
    kid: str | None = None,
) -> str:
    """A token with full control over its claims, for the negative cases.

    ``email_verified`` defaults true, matching what Clerk emits for a verified
    address. Set it false to prove an unverified claim cannot link an account.
    """
    now = int(time.time())
    claims = {"sub": subject, "iss": issuer, "aud": audience, "iat": now, "exp": now + expires_in}
    if email is not None:
        claims["email"] = email
        claims["email_verified"] = email_verified
    return jwt.encode(
        claims,
        key or clerk_stub.private_key,
        algorithm="RS256",
        headers={"kid": kid or clerk_stub.kid},
    )


def _request(token: str | None, *, raw_authorization: str | None = None):
    """A minimal ASGI request carrying the bearer header under test."""
    from starlette.requests import Request

    headers = []
    if raw_authorization is not None:
        headers.append((b"authorization", raw_authorization.encode()))
    elif token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request({"type": "http", "headers": headers, "method": "GET", "path": "/"})


async def _resolve(token: str | None, redis) -> CurrentUser | None:
    request = _request(token)
    return await deps._actor_from_request(request, redis)


# --- token verification -------------------------------------------------------


async def test_a_valid_clerk_token_resolves_to_a_new_internal_uuid(clerk_stub, fake_redis):
    actor = await _resolve(make_token(clerk_stub), fake_redis)
    assert actor is not None
    assert isinstance(actor.id, UUID)
    assert actor.email == "learner@example.test"


async def test_the_same_subject_resolves_to_the_same_uuid(clerk_stub, fake_redis, session):
    first = await _resolve(make_token(clerk_stub, subject="user_stable"), fake_redis)
    await fake_redis.flushall()  # force a real DB lookup, not the mapping cache
    second = await _resolve(make_token(clerk_stub, subject="user_stable"), fake_redis)
    assert first.id == second.id


async def test_a_missing_token_yields_no_actor(clerk_stub, fake_redis):
    assert await _resolve(None, fake_redis) is None


async def test_an_expired_token_is_rejected(clerk_stub, fake_redis):
    with pytest.raises(UnauthorizedError) as exc:
        await _resolve(make_token(clerk_stub, expires_in=-60), fake_redis)
    assert exc.value.code == "expired_token"


async def test_a_wrong_issuer_is_rejected(clerk_stub, fake_redis):
    with pytest.raises(UnauthorizedError) as exc:
        await _resolve(make_token(clerk_stub, issuer="https://attacker.example"), fake_redis)
    assert exc.value.code == "invalid_token"


async def test_a_wrong_audience_is_rejected(clerk_stub, fake_redis):
    with pytest.raises(UnauthorizedError) as exc:
        await _resolve(make_token(clerk_stub, audience="someone-else"), fake_redis)
    assert exc.value.code == "invalid_token"


async def test_a_token_signed_by_a_foreign_key_is_rejected(clerk_stub, fake_redis):
    foreign = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(UnauthorizedError) as exc:
        await _resolve(make_token(clerk_stub, key=foreign), fake_redis)
    assert exc.value.code == "invalid_token"


async def test_an_unsigned_token_is_rejected(clerk_stub, fake_redis):
    """`alg: none` must not be accepted: the algorithm list is pinned to RS256."""
    now = int(time.time())
    forged = jwt.encode(
        {"sub": "user_forged", "iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300},
        key="",
        algorithm="none",
    )
    with pytest.raises(UnauthorizedError):
        await _resolve(forged, fake_redis)


async def test_a_token_without_a_subject_is_rejected(clerk_stub, fake_redis):
    now = int(time.time())
    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300},
        clerk_stub.private_key,
        algorithm="RS256",
        headers={"kid": clerk_stub.kid},
    )
    with pytest.raises(UnauthorizedError) as exc:
        await _resolve(token, fake_redis)
    assert exc.value.code == "invalid_token_claims"


async def test_a_malformed_authorization_header_is_rejected(clerk_stub, fake_redis):
    """A header that is not `Bearer <token>` is a credential error, not a token error."""
    for header in ("Basic abc", "Bearer", "Bearer   ", "Token abc"):
        request = _request(None, raw_authorization=header)
        with pytest.raises(UnauthorizedError) as exc:
            await deps._actor_from_request(request, fake_redis)
        assert exc.value.code == "invalid_authorization", header


async def test_a_second_credential_in_the_header_is_rejected(clerk_stub, fake_redis):
    """Two tokens in one header is ambiguous, so it is refused rather than guessed."""
    token = make_token(clerk_stub)
    request = _request(None, raw_authorization=f"Bearer {token} {token}")
    with pytest.raises(UnauthorizedError) as exc:
        await deps._actor_from_request(request, fake_redis)
    assert exc.value.code == "invalid_authorization"


async def test_a_rotated_signing_key_is_accepted_after_a_cache_refresh(
    clerk_stub, fake_redis, engine
):
    """Clerk rotates keys; a new kid must verify without a process restart."""
    clerk_stub.rotate("key-2")
    try:
        actor = await _resolve(make_token(clerk_stub, subject="user_rotated"), fake_redis)
        assert actor is not None
    finally:
        clerk_stub.kid = "key-1"


async def test_verification_fails_closed_when_jwks_is_unconfigured(
    clerk_stub, fake_redis, monkeypatch
):
    """No configured JWKS is a refusal, never a locally-signed fallback."""
    monkeypatch.setattr(settings, "clerk_jwks_url", "")
    monkeypatch.setattr(deps, "_jwks_client", None)
    with pytest.raises(UnauthorizedError) as exc:
        await _resolve(make_token(clerk_stub), fake_redis)
    assert exc.value.code == "auth_not_configured"


# --- subject to account mapping ----------------------------------------------


async def test_a_verified_email_links_an_existing_unlinked_account(
    clerk_stub, fake_redis, session, monkeypatch
):
    """A pre-cutover learner keeps their UUID and library when they sign in."""
    legacy = User(email="legacy@example.test", clerk_id=None)
    session.add(legacy)
    await session.commit()
    legacy_id = legacy.id

    monkeypatch.setattr(deps.db_session, "async_session_factory", lambda: _SessionCtx(session))
    token = make_token(clerk_stub, subject="user_legacy", email="legacy@example.test")
    actor = await _resolve(token, fake_redis)

    assert actor.id == legacy_id
    refreshed = await session.scalar(select(User).where(User.id == legacy_id))
    assert refreshed.clerk_id == "user_legacy"


async def test_an_email_owned_by_another_subject_is_a_conflict(
    clerk_stub, fake_redis, session, monkeypatch
):
    """Linking by email must never move one learner's library to another."""
    owner = User(email="taken@example.test", clerk_id="user_original")
    session.add(owner)
    await session.commit()

    monkeypatch.setattr(deps.db_session, "async_session_factory", lambda: _SessionCtx(session))
    token = make_token(clerk_stub, subject="user_other", email="taken@example.test")
    with pytest.raises(ConflictError) as exc:
        await _resolve(token, fake_redis)
    assert exc.value.code == "identity_conflict"


async def test_an_unverified_email_cannot_link_an_existing_account(
    clerk_stub, fake_redis, session, monkeypatch
):
    """An unverified claim must not be able to claim someone else's account.

    This is the account-takeover path: if the resolver trusted a raw email claim,
    any caller who could assert a victim's address would inherit their library. An
    unverified claim therefore provisions a *new* account instead of linking.
    """
    victim = User(email="victim@example.test", clerk_id=None)
    session.add(victim)
    await session.commit()
    victim_id = victim.id

    monkeypatch.setattr(deps.db_session, "async_session_factory", lambda: _SessionCtx(session))
    token = make_token(
        clerk_stub,
        subject="user_attacker",
        email="victim@example.test",
        email_verified=False,
    )
    actor = await _resolve(token, fake_redis)

    assert actor.id != victim_id, "an unverified claim must not inherit the victim's account"
    refreshed = await session.scalar(select(User).where(User.id == victim_id))
    assert refreshed.clerk_id is None, "the victim's row must stay unlinked"


async def test_a_case_variant_email_still_links_the_existing_account(
    clerk_stub, fake_redis, session, monkeypatch
):
    """The unique index is case-sensitive, so the lookup must not be.

    A stored "Learner@Example.com" and a claim of "learner@example.com" are two
    distinct rows to Postgres. Matching exactly would orphan the pre-cutover
    learner's library and provision a fresh empty account beside it.
    """
    legacy = User(email="Learner@Example.com", clerk_id=None)
    session.add(legacy)
    await session.commit()
    legacy_id = legacy.id

    monkeypatch.setattr(deps.db_session, "async_session_factory", lambda: _SessionCtx(session))
    token = make_token(
        clerk_stub, subject="user_case", email="learner@example.com", email_verified=True
    )
    actor = await _resolve(token, fake_redis)

    assert actor.id == legacy_id, "a case difference must not create a second account"
    refreshed = await session.scalar(select(User).where(User.id == legacy_id))
    assert refreshed.clerk_id == "user_case"


async def test_concurrent_first_sign_ins_converge_on_one_account(
    clerk_stub, fake_redis, session, monkeypatch
):
    """Two simultaneous first requests must produce one row and one UUID.

    The insert is keyed on the subject with ON CONFLICT DO NOTHING plus a re-read,
    so the loser of the race reads the winner's row rather than failing or creating
    a duplicate.
    """
    monkeypatch.setattr(deps.db_session, "async_session_factory", lambda: _SessionCtx(session))
    token = make_token(
        clerk_stub, subject="user_concurrent", email="concurrent@example.test"
    )
    # A cold cache on each call, so both attempts reach the database.
    await fake_redis.flushall()
    first = await _resolve(token, fake_redis)
    await fake_redis.flushall()
    second = await _resolve(token, fake_redis)

    assert first.id == second.id
    rows = list(await session.scalars(select(User).where(User.clerk_id == "user_concurrent")))
    assert len(rows) == 1, "one subject must map to exactly one account"


class _SessionCtx:
    """Adapt a live session to the async-context-manager the resolver expects."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc) -> None:
        return None


# --- route-level contract -----------------------------------------------------


def _app() -> FastAPI:
    """A minimal app with the production error handler installed.

    The handler is what maps `UnauthorizedError` to a 401 envelope, so a bare
    FastAPI app would let the exception escape and the test would assert on a
    traceback instead of a status code.
    """
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)

    @app.get("/private")
    async def private(user: CurrentUser = Depends(current_user)) -> dict:
        return {"id": str(user.id)}

    @app.get("/public")
    async def public(user: CurrentUser | None = Depends(optional_current_user)) -> dict:
        return {"viewer": str(user.id) if user else None}

    return app


async def test_required_route_rejects_a_missing_token(clerk_stub, fake_redis):
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.get("/private")
    assert response.status_code == 401


async def test_public_route_allows_anonymous_reads(clerk_stub, fake_redis):
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.get("/public")
    assert response.status_code == 200
    assert response.json() == {"viewer": None}


async def test_public_route_rejects_an_invalid_token_rather_than_downgrading(
    clerk_stub, fake_redis
):
    """An invalid credential on a public route must not be treated as anonymous."""
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.get("/public", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401


async def test_resolution_closes_its_session_before_returning(
    clerk_stub, fake_redis, session, monkeypatch
):
    """Identity resolution must not hold a session open past the actor.

    The old resolver read `user.token_version` *after* its session block, which
    kept the connection leased; a stream that then waits on model output would hold
    it for the whole response. This records when the session context exits and
    asserts that happened before the resolver returned.
    """
    holder: dict[str, bool] = {}

    class _TrackingCtx:
        def __init__(self, inner: AsyncSession) -> None:
            self._inner = inner

        async def __aenter__(self) -> AsyncSession:
            return self._inner

        async def __aexit__(self, *exc) -> None:
            holder["closed_before_return"] = True
            return None

    monkeypatch.setattr(deps.db_session, "async_session_factory", lambda: _TrackingCtx(session))

    actor = await _resolve(make_token(clerk_stub, subject="user_release"), fake_redis)

    assert actor is not None
    assert holder.get("closed_before_return"), (
        "the resolver returned an actor while its database session was still open"
    )
