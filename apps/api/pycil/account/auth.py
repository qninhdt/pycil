"""Clerk identity verified by configured issuer, never by an email claim."""

import asyncio
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid7

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from pycil.account.lifecycle import clerk_user
from pycil.account.models import User
from pycil.account.plans import Plan
from pycil.dependencies import Session
from pycil.http import Problem


class Identity:
    def __init__(self, deployment):
        self.deployment = deployment
        self.keys = jwt.PyJWKClient(deployment.clerk_jwks_url)

    async def subject(self, token: str) -> str:
        try:
            key = await asyncio.to_thread(self.keys.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.deployment.clerk_issuer,
                audience=self.deployment.clerk_audience,
                options={
                    "require": ["exp", "sub", "iss"],
                    "verify_aud": self.deployment.clerk_audience is not None,
                },
            )
            subject = claims["sub"]
            if not isinstance(subject, str) or not subject.strip() or len(subject) > 255:
                raise jwt.InvalidTokenError("invalid subject")
            return subject
        except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
            raise Problem(401, "invalid_credentials") from exc


class ActorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: UUID
    clerk_subject: str
    display_name: str | None
    plan: Plan
    settings: dict
    cycle_anchor: datetime
    created_at: datetime


bearer = HTTPBearer(auto_error=False, scheme_name="ClerkBearer", bearerFormat="JWT")
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


async def actor(request: Request, session: Session, credentials: Credentials) -> ActorContext:
    if request.headers.get("authorization") is None:
        raise Problem(401, "authentication_required")
    if credentials is None or not credentials.credentials.strip():
        raise Problem(401, "invalid_credentials")
    subject = await request.app.state.identity.subject(credentials.credentials)
    cache = session.info.get("cache")
    key = f"actor:{subject}"
    if cache and (context := await cache.get(key, ActorContext)) is not None:
        return context
    # Verify missing identities with Clerk before provisioning, preventing stale
    # signed tokens from recreating an account whose identity was deleted.
    async with session.begin():
        user = await session.scalar(select(User).where(User.clerk_subject == subject))
    if user is None:
        now = datetime.now(UTC)
        await clerk_user(request.app.state.http, request.app.state.deployment, subject)
        async with session.begin():
            await session.execute(
                insert(User)
                .values(
                    id=uuid7(),
                    clerk_subject=subject,
                    cycle_anchor=now,
                    created_at=now,
                    settings={},
                )
                .on_conflict_do_nothing(index_elements=[User.clerk_subject])
            )
            user = await session.scalar(select(User).where(User.clerk_subject == subject))
    context = ActorContext.model_validate(user)
    if cache:
        await cache.put(key, context, cache.policy.actor_ttl_seconds)
    return context


Actor = Annotated[ActorContext, Depends(actor)]


async def optional_actor(
    request: Request, session: Session, credentials: Credentials
) -> ActorContext | None:
    if request.headers.get("authorization") is None:
        return None
    return await actor(request, session, credentials)


Viewer = Annotated[ActorContext | None, Depends(optional_actor)]
