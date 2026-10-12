"""Clerk identity verified by configured issuer, never by an email claim."""

import asyncio
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid7

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from pycil.account.handles import generate_handle
from pycil.account.lifecycle import clerk_user
from pycil.account.models import User
from pycil.account.plans import Plan
from pycil.dependencies import Session
from pycil.http import Problem
from pycil.library.tree import provision_library
from pycil.logging import bind_contextvars, get_logger

logger = get_logger(__name__)


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
            logger.warning("auth_token_verification_failed", error_type=type(exc).__name__)
            raise Problem(401, "invalid_credentials") from exc


class ActorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: UUID
    clerk_subject: str
    display_name: str | None
    handle: str | None
    plan: Plan
    settings: dict
    cycle_anchor: datetime
    created_at: datetime


bearer = HTTPBearer(auto_error=False, scheme_name="ClerkBearer", bearerFormat="JWT")
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


async def actor(request: Request, session: Session, credentials: Credentials) -> ActorContext:
    if request.headers.get("authorization") is None:
        logger.warning("auth_credentials_missing")
        raise Problem(401, "authentication_required")
    if credentials is None or not credentials.credentials.strip():
        logger.warning("auth_credentials_missing")
        raise Problem(401, "invalid_credentials")
    subject = await request.app.state.identity.subject(credentials.credentials)
    cache = session.info.get("cache")
    key = f"actor:v3:{subject}"
    if cache and (context := await cache.get(key, ActorContext)) is not None:
        bind_contextvars(actor_id=str(context.id))
        return context
    # Verify missing identities with Clerk before provisioning, preventing stale
    # signed tokens from recreating an account whose identity was deleted.
    async with session.begin():
        user = await session.scalar(select(User).where(User.clerk_subject == subject))
    if user is None or user.display_name is None or user.handle is None:
        now = datetime.now(UTC)
        identity = await clerk_user(request.app.state.http, request.app.state.deployment, subject)
        name = " ".join((identity.get(key) or "").strip() for key in ("first_name", "last_name"))
        name = name.strip()[:255].strip() or "Pycil learner"
        identifier = uuid7() if user is None else user.id
        handle_name = user.display_name if user and user.display_name else name
        async with session.begin():
            for _ in range(5):
                statement = insert(User).values(
                    id=identifier,
                    clerk_subject=subject,
                    display_name=name,
                    handle=generate_handle(handle_name),
                    cycle_anchor=now,
                    created_at=now,
                    settings={},
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[User.clerk_subject],
                    set_={
                        "display_name": func.coalesce(
                            User.display_name, statement.excluded.display_name
                        ),
                        "handle": func.coalesce(User.handle, statement.excluded.handle),
                    },
                ).returning(User)
                try:
                    async with session.begin_nested():
                        user = await session.scalar(
                            statement.execution_options(populate_existing=True)
                        )
                    break
                except IntegrityError as exc:
                    if getattr(exc.orig, "sqlstate", None) != "23505":
                        raise
                    logger.warning("account_handle_collision")
            else:
                raise Problem(503, "handle_generation_failed")
            await provision_library(session, user.id)
            logger.info("account_provisioned", user_id=str(user.id))
    context = ActorContext.model_validate(user)
    if cache:
        await cache.put(key, context, cache.policy.actor_ttl_seconds)
    bind_contextvars(actor_id=str(context.id))
    return context


Actor = Annotated[ActorContext, Depends(actor)]


async def optional_actor(
    request: Request, session: Session, credentials: Credentials
) -> ActorContext | None:
    if request.headers.get("authorization") is None:
        return None
    return await actor(request, session, credentials)


Viewer = Annotated[ActorContext | None, Depends(optional_actor)]
