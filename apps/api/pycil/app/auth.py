"""Clerk identity verified by configured issuer, never by an email claim."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid7

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from pycil.account.handles import generate_handle
from pycil.account.models import User
from pycil.app.dependencies import Session
from pycil.app.http import Problem
from pycil.infrastructure.clerk import IdentityServiceUnavailable, InvalidIdentityError, clerk_user
from pycil.library.tree import provision_library
from pycil.observability import bind_contextvars, get_logger

logger = get_logger(__name__)


bearer = HTTPBearer(auto_error=False, scheme_name="ClerkBearer", bearerFormat="JWT")
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


async def current_user_id(request: Request, session: Session, credentials: Credentials) -> UUID:
    if request.headers.get("authorization") is None:
        logger.warning("auth_credentials_missing")
        raise Problem(401, "authentication_required")
    if credentials is None or not credentials.credentials.strip():
        logger.warning("auth_credentials_missing")
        raise Problem(401, "invalid_credentials")
    try:
        subject = await request.app.state.identity.subject(credentials.credentials)
    except InvalidIdentityError:
        raise Problem(401, "invalid_credentials") from None
    store = getattr(request.app.state, "user_id_store", None)
    if store is not None and (identifier := store.get(subject)) is not None:
        bind_contextvars(user_id=str(identifier))
        return identifier
    # Verify missing identities with Clerk before provisioning, preventing stale
    # signed tokens from recreating an account whose identity was deleted.
    async with session.begin():
        user = await session.scalar(select(User).where(User.clerk_id == subject))
    if user is None or user.display_name is None or user.handle is None:
        now = datetime.now(UTC)
        try:
            identity = await clerk_user(
                request.app.state.http,
                request.app.state.deployment.clerk_secret_key.get_secret_value(),
                subject,
                timeout=request.app.state.config.account.profile_timeout_seconds,
            )
        except InvalidIdentityError:
            raise Problem(401, "invalid_credentials") from None
        except IdentityServiceUnavailable:
            raise Problem(503, "identity_service_unavailable") from None
        name = " ".join((identity.get(key) or "").strip() for key in ("first_name", "last_name"))
        name = name.strip()[:255].strip() or "Pycil learner"
        identifier = uuid7() if user is None else user.id
        handle_name = user.display_name if user and user.display_name else name
        async with session.begin():
            for _ in range(5):
                statement = insert(User).values(
                    id=identifier,
                    clerk_id=subject,
                    display_name=name,
                    handle=generate_handle(handle_name),
                    cycle_anchor=now,
                    created_at=now,
                    settings={},
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[User.clerk_id],
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
            assert user is not None, "user must be provisioned"
            await provision_library(session, user.id)
            logger.info("account_provisioned", user_id=str(user.id))
    assert user is not None
    if store is not None:
        store.put(subject, user.id)
    bind_contextvars(user_id=str(user.id))
    return user.id


UserId = Annotated[UUID, Depends(current_user_id)]


async def optional_user_id(
    request: Request, session: Session, credentials: Credentials
) -> UUID | None:
    if request.headers.get("authorization") is None:
        return None
    return await current_user_id(request, session, credentials)


Viewer = Annotated[UUID | None, Depends(optional_user_id)]
