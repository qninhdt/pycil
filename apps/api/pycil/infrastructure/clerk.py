"""Clerk verification and transport; account provisioning belongs to the account domain."""

import asyncio
from typing import TypedDict, cast
from urllib.parse import quote

import httpx
import jwt
from structlog import get_logger

logger = get_logger(__name__)


class ClerkEmailAddress(TypedDict, total=False):
    id: str
    email_address: str
    verification: dict[str, object]


class ClerkUserProfile(TypedDict, total=False):
    id: str
    first_name: str | None
    last_name: str | None
    email_addresses: list[ClerkEmailAddress]


class InvalidIdentityError(ValueError):
    pass


class IdentityServiceUnavailable(RuntimeError):
    pass


class Identity:
    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        audience: str | None = None,
        *,
        timeout: float = 30,
        lifespan: float = 300,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.keys = jwt.PyJWKClient(jwks_url, timeout=timeout, lifespan=lifespan)

    async def subject(self, token: str) -> str:
        try:
            key = await asyncio.to_thread(self.keys.get_signing_key_from_jwt, token)
            claims: dict[str, object] = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "require": ["exp", "sub", "iss"],
                    "verify_aud": self.audience is not None,
                },
            )
            subject = claims.get("sub")
            if not isinstance(subject, str) or not subject.strip() or len(subject) > 255:
                raise jwt.InvalidTokenError("invalid subject")
            return subject
        except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
            logger.warning("auth_token_verification_failed", error_type=type(exc).__name__)
            raise InvalidIdentityError("invalid credentials") from exc


async def clerk_user(
    http: httpx.AsyncClient, secret_key: str, subject: str, *, timeout: float
) -> ClerkUserProfile:
    try:
        response = await http.request(
            "GET",
            "https://api.clerk.com/v1/users/" + quote(subject, safe=""),
            headers={"Authorization": "Bearer " + secret_key},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        logger.error("clerk_api_request_failed", error_type=type(exc).__name__, subject=subject)
        raise IdentityServiceUnavailable("identity service unavailable") from None
    if response.status_code == 404:
        logger.warning("clerk_user_not_found", subject=subject)
        raise InvalidIdentityError("invalid credentials")
    if not response.is_success:
        logger.error("clerk_api_request_failed", status_code=response.status_code, subject=subject)
        raise IdentityServiceUnavailable("identity service unavailable")
    try:
        raw: object = response.json()
        if not isinstance(raw, dict):
            raise ValueError("invalid identity profile")
        data: dict[str, object] = cast(dict[str, object], raw)
        if any(
            data.get(key) is not None and not isinstance(data.get(key), str)
            for key in ("first_name", "last_name")
        ):
            raise ValueError("invalid identity profile")
    except ValueError as exc:
        logger.error("clerk_api_request_failed", error_type=type(exc).__name__, subject=subject)
        raise IdentityServiceUnavailable("identity service unavailable") from None
    return cast(ClerkUserProfile, data)
