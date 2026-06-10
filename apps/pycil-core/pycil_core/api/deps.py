"""Shared FastAPI dependencies for routes."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from pycil_core.auth import CurrentUser, get_current_user
from pycil_core.db import get_session
from pycil_core.services.redis_pool import get_redis

UserDep = Annotated[CurrentUser, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def require_admin(user: UserDep) -> CurrentUser:
    """Authoritative per-request admin gate.

    `get_current_user` already re-read the DB row and applied the ban lockout,
    so `user.role` reflects live DB state — the JWT `role` claim is edge
    convenience only and never grants privilege here.
    """
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin_required")
    return user


AdminDep = Annotated[CurrentUser, Depends(require_admin)]


async def _placeholder() -> AsyncGenerator[None, None]:
    yield None
