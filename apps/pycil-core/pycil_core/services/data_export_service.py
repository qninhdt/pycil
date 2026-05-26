"""GDPR data export (P12 phase 1).

Aggregates every row owned by a user into a JSON archive: profile,
decks, terms, definitions, learning history, chat history, ToS acks,
billing events, admin actions targeting them.

Returns AsyncIterator[bytes] yielding NDJSON rows so the response can
stream without buffering the full dump in memory.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_TABLES_FOR_USER = [
    ("profile",        "SELECT * FROM users WHERE id = :uid"),
    ("nodes",          "SELECT * FROM nodes WHERE author_id = :uid"),
    ("user_term_stats","SELECT * FROM user_term_stats WHERE user_id = :uid"),
    ("user_term_jobs", "SELECT * FROM user_term_jobs WHERE user_id = :uid"),
    ("learning_sessions",
        "SELECT * FROM learning_sessions WHERE user_id = :uid"),
    ("chat_sessions",  "SELECT * FROM chat_sessions WHERE user_id = :uid"),
    ("user_tos_acks",  "SELECT * FROM user_tos_acks WHERE user_id = :uid"),
    ("term_notes",     "SELECT * FROM term_notes WHERE user_id = :uid"),
    ("definition_overrides",
        "SELECT * FROM definition_overrides WHERE user_id = :uid"),
    ("activity_events",
        "SELECT * FROM activity_events WHERE user_id = :uid"),
    ("admin_actions_about_me",
        "SELECT * FROM admin_actions WHERE target_user_id = :uid"),
]


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


async def export(
    session: AsyncSession, user_id: UUID
) -> AsyncIterator[bytes]:
    yield (json.dumps({"_meta": {"version": 1, "user_id": str(user_id)}}) + "\n").encode()
    for table_name, sql in _TABLES_FOR_USER:
        try:
            rows = (await session.execute(text(sql), {"uid": user_id})).mappings().all()
        except Exception as exc:  # noqa: BLE001
            yield (
                json.dumps(
                    {"_table": table_name, "_error": str(exc)[:200]}
                ) + "\n"
            ).encode()
            continue
        for r in rows:
            payload = {k: _serialize(v) for k, v in dict(r).items()}
            yield (json.dumps({"_table": table_name, "row": payload}) + "\n").encode()
