"""GDPR data export (P12 phase 1).

Aggregates every row owned by a user into a JSON archive: profile,
decks, terms, definitions, learning history, chat history, ToS acks,
billing events, admin actions targeting them.

Returns AsyncIterator[bytes] yielding NDJSON rows so the response can
stream without buffering the full dump in memory.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from shared.db import (
    ActivityEvent,
    AdminAction,
    ChatSession,
    DefinitionOverride,
    Node,
    TermNote,
    User,
    UserTermJob,
    UserTermStat,
    UserTosAck,
)
from sqlalchemy import select, text
from sqlmodel.ext.asyncio.session import AsyncSession

_TABLES_FOR_USER: list[tuple[str, Callable[[UUID], Any] | str]] = [
    ("profile", lambda uid: select(User).where(User.id == uid)),
    ("nodes", lambda uid: select(Node).where(Node.author_id == uid)),
    ("user_term_stats", lambda uid: select(UserTermStat).where(UserTermStat.user_id == uid)),
    ("user_term_jobs", lambda uid: select(UserTermJob).where(UserTermJob.user_id == uid)),
    ("learning_sessions", "SELECT * FROM learning_sessions WHERE user_id = :uid"),
    ("chat_sessions", lambda uid: select(ChatSession).where(ChatSession.user_id == uid)),
    ("user_tos_acks", lambda uid: select(UserTosAck).where(UserTosAck.user_id == uid)),
    ("term_notes", lambda uid: select(TermNote).where(TermNote.user_id == uid)),
    (
        "definition_overrides",
        lambda uid: select(DefinitionOverride).where(DefinitionOverride.user_id == uid),
    ),
    ("activity_events", lambda uid: select(ActivityEvent).where(ActivityEvent.user_id == uid)),
    (
        "admin_actions_about_me",
        lambda uid: select(AdminAction).where(AdminAction.target_user_id == uid),
    ),
]


def _serialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_serialize(v) for v in value]
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


async def export(
    session: AsyncSession, user_id: UUID
) -> AsyncIterator[bytes]:
    yield (json.dumps({"_meta": {"version": 1, "user_id": str(user_id)}}) + "\n").encode()
    for table_name, query in _TABLES_FOR_USER:
        try:
            if callable(query):
                rows = (await session.exec(query(user_id))).all()
            else:
                rows = (
                    await session.execute(text(query), {"uid": user_id})
                ).mappings().all()
        except Exception as exc:  # noqa: BLE001
            yield (
                json.dumps(
                    {"_table": table_name, "_error": str(exc)[:200]}
                ) + "\n"
            ).encode()
            continue
        for row in rows:
            if hasattr(row, "model_dump"):
                raw_payload = row.model_dump()
            else:
                raw_payload = dict(row)
            payload = {k: _serialize(v) for k, v in raw_payload.items()}
            yield (json.dumps({"_table": table_name, "row": payload}) + "\n").encode()
