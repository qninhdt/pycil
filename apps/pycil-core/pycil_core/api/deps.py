"""Shared FastAPI dependencies for routes."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlmodel.ext.asyncio.session import AsyncSession

from pycil_core.auth import CurrentUser, get_current_user
from pycil_core.db import get_session
from pycil_core.services.redis_pool import get_redis

UserDep = Annotated[CurrentUser, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def _placeholder() -> AsyncGenerator[None, None]:
    yield None
