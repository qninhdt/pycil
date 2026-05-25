"""Shared FastAPI dependencies for routes."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pycil_core.auth import CurrentUser, get_current_user
from pycil_core.db import get_session

UserDep = Annotated[CurrentUser, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _placeholder() -> AsyncGenerator[None, None]:
    yield None
