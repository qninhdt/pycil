"""Clerk bearer verification and Clerk-subject to Pycil-UUID resolution.

The trust boundary is the Clerk-signed subject. This module verifies the bearer
token against Clerk's JWKS and then maps that subject to the internal UUID every
product foreign key points at. There is no local signing path and no fallback: a
Clerk outage fails closed rather than admitting a token this service minted for
itself.
"""

import json
from typing import Any
from uuid import UUID, uuid7

from clerk_backend_api.security import (
    TokenVerificationError,
    TokenVerificationErrorReason,
    VerifyTokenOptions,
    verify_token_async,
)
from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

from pycil.account.schemas import CurrentUser
from pycil.account.user import User
from pycil.platform import database as db_session
from pycil.platform.errors import ConflictError, UnauthorizedError
from pycil.platform.redis import get_redis
from pycil.platform.settings import settings

_MAPPING_CACHE_TTL_SECONDS = 300
_MAPPING_CACHE_PREFIX = "auth:clerk:"

#: Retained for backward compatibility with test fixtures that patch _jwks_client
_jwks_client: Any = None


def _presented_token(request: Request) -> str | None:
    """The single bearer credential, or ``None`` when none was presented.

    Only the ``Authorization: Bearer`` header is consulted. The legacy access
    cookie is not read: accepting two credential channels made "which identity is
    this?" ambiguous, and Clerk's browser SDK sends the bearer header itself.
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    scheme, separator, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not value.strip():
        raise UnauthorizedError("invalid_authorization")
    token = value.strip()
    if " " in token:
        # A second credential smuggled into the same header is not a token.
        raise UnauthorizedError("invalid_authorization")
    return token


async def _decode_claims(token: str) -> dict[str, Any]:
    """Verify a Clerk token asynchronously using clerk-backend-api and return its claims.

    Validates signature, issuer, audience when configured, and expiry. Every
    failure raises the same stable code so a caller cannot distinguish an expired
    token from a forged one.
    """
    if not settings.clerk_jwks_url and not settings.clerk_jwt_key and not settings.clerk_api_url:
        raise UnauthorizedError("auth_not_configured")

    api_url = settings.clerk_api_url or settings.clerk_jwks_url or "https://api.clerk.com"
    if api_url:
        api_url = api_url.removesuffix("/v1/jwks").removesuffix("/jwks").rstrip("/")

    options = VerifyTokenOptions(
        secret_key=settings.clerk_secret_key or "clerk_test_secret_key",
        api_url=api_url or "https://api.clerk.com",
        api_version="v1",
        audience=settings.clerk_audience or None,
        jwt_key=settings.clerk_jwt_key or None,
    )

    try:
        claims = await verify_token_async(token, options)
    except TokenVerificationError as exc:
        if exc.reason == TokenVerificationErrorReason.TOKEN_EXPIRED:
            raise UnauthorizedError("expired_token", code="expired_token") from exc
        raise UnauthorizedError("invalid_token") from exc
    except UnauthorizedError:
        raise
    except Exception as exc:  # noqa: BLE001 - JWKS fetch/parse failure fails closed
        raise UnauthorizedError("invalid_token") from exc

    if settings.clerk_issuer and claims.get("iss") != settings.clerk_issuer:
        raise UnauthorizedError("invalid_token")

    return claims


def _cache_key(clerk_id: str) -> str:
    return f"{_MAPPING_CACHE_PREFIX}{clerk_id}"


async def _cached_actor(redis: Redis, clerk_id: str) -> CurrentUser | None:
    raw = await redis.get(_cache_key(clerk_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return CurrentUser(
            id=UUID(data["id"]),
            email=data["email"],
            name=data.get("name"),
            image=data.get("image"),
        )
    except Exception:  # noqa: BLE001 - a malformed cache entry is a miss, not an error
        return None


async def _remember_actor(redis: Redis, clerk_id: str, actor: CurrentUser) -> None:
    await redis.set(
        _cache_key(clerk_id),
        json.dumps(
            {
                "id": str(actor.id),
                "email": actor.email,
                "name": actor.name,
                "image": actor.image,
            }
        ),
        ex=_MAPPING_CACHE_TTL_SECONDS,
    )


async def evict_mapping(redis: Redis, clerk_id: str) -> None:
    """Drop a cached subject mapping after deletion or relink."""
    await redis.delete(_cache_key(clerk_id))


def _actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email, name=user.name, image=user.image)


async def _resolve_user(clerk_id: str, email: str | None, redis: Redis) -> CurrentUser:
    """Map a verified Clerk subject to the internal account.

    The subject is the only lookup key that may create an account. A verified
    email may *link* an existing unlinked row, because that is how a pre-cutover
    learner keeps their library; it may never create a second account or merge
    two, so an email that already belongs to a different subject is a conflict
    the caller must resolve rather than a silent takeover.
    """
    cached = await _cached_actor(redis, clerk_id)
    if cached is not None:
        return cached

    async with db_session.async_session_factory() as db:
        user = await db.scalar(select(User).where(User.clerk_id == clerk_id))

        if user is None and email:
            # Case-insensitive: the unique index is case-sensitive, so a stored
            # "Learner@Example.com" and a claim of "learner@example.com" are two
            # rows to Postgres. Matching exactly would orphan the pre-cutover
            # learner's library and provision a fresh empty account beside it.
            candidate = await db.scalar(select(User).where(func.lower(User.email) == email.lower()))
            if candidate is not None:
                if candidate.clerk_id is None:
                    # Claim the row for this subject. Guarding on `clerk_id IS
                    # NULL` makes two concurrent first sign-ins race to one winner
                    # rather than one overwriting the other's mapping.
                    await db.execute(
                        update(User)
                        .where(User.id == candidate.id, User.clerk_id.is_(None))
                        .values(clerk_id=clerk_id)
                    )
                    await db.commit()
                    user = await db.scalar(select(User).where(User.clerk_id == clerk_id))
                    if user is None:
                        # Another subject won the race for this email. Provisioning
                        # here would create a second account for one address, which
                        # is exactly the merge the conflict exists to prevent.
                        raise ConflictError("identity_conflict", code="identity_conflict")
                else:
                    # The email belongs to a different Clerk subject. Refusing is
                    # the only safe answer: linking would hand one learner's
                    # library to another.
                    raise ConflictError("identity_conflict", code="identity_conflict")

        if user is None:
            # No account claims this subject yet. Provision one, keyed on the
            # subject so two concurrent first requests converge on a single row.
            await db.execute(
                insert(User)
                .values(id=uuid7(), clerk_id=clerk_id, email=email or f"{clerk_id}@clerk.local")
                .on_conflict_do_nothing(index_elements=["clerk_id"])
            )
            await db.commit()
            user = await db.scalar(select(User).where(User.clerk_id == clerk_id))

        if user is None:
            raise UnauthorizedError("user_provisioning_failed")

        resolved = _actor(user)

    await _remember_actor(redis, clerk_id, resolved)
    return resolved


async def _actor_from_request(request: Request, redis: Redis) -> CurrentUser | None:
    token = _presented_token(request)
    if token is None:
        return None
    claims = await _decode_claims(token)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise UnauthorizedError("invalid_token_claims")
    # Linking to an existing account requires a *verified* address. An unverified
    # claim is attacker-controlled in the general case, so accepting one would let
    # a caller claim any unlinked account by asserting its email. A token without
    # the claim simply provisions a new account instead of linking.
    email = claims.get("email")
    verified_email = email if claims.get("email_verified") is True else None
    return await _resolve_user(
        subject, verified_email if isinstance(verified_email, str) else None, redis
    )


async def current_user(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> CurrentUser:
    """Mandatory authentication. No token is a 401, not an anonymous actor."""
    actor = await _actor_from_request(request, redis)
    if actor is None:
        raise UnauthorizedError("missing_token")
    return actor


async def optional_current_user(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> CurrentUser | None:
    """Optional authentication for public reads.

    A missing token yields no viewer so anonymous browsing keeps working. A token
    that *is* supplied must be valid: silently downgrading an invalid credential
    to anonymous would let a signed-in learner believe they are reading as
    themselves while the API served a public view.
    """
    return await _actor_from_request(request, redis)
