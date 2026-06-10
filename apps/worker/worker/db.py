"""Async DB session for worker jobs."""
from __future__ import annotations

import json
from functools import partial

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from worker.config import get_settings

_settings = get_settings()

# Serialize JSONB writes with `default=str` so UUID/datetime values in a job
# `result` dict round-trip as strings — matching the pre-conversion
# `json.dumps(result, default=str)` in lifecycle.mark_job. Without this the
# ORM `.values(result=...)` path raises TypeError on a UUID question_id.
_json_serializer = partial(json.dumps, default=str)

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    json_serializer=_json_serializer,
)

SessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)
