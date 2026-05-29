"""Chat-with-AI study mode session management.

LLM streaming over SSE on pycil-core (NOT a worker job — instant streaming).
Reuses existing SSE infra. Per-session technical caps; no per-user $ cap
in v0.2 (alert-only at $100/day org-wide via phase 15 Sentry).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_INPUT_TOKEN_CAP = 20_000
_OUTPUT_TOKEN_CAP = 8_000


async def create_session(
    session: AsyncSession,
    *,
    user_id: UUID,
    deck_id: UUID | None,
) -> UUID:
    if deck_id is not None:
        owns = (
            await session.execute(
                text(
                    """
                    SELECT 1 FROM nodes
                     WHERE id = :did
                       AND type = 'DECK'
                       AND (author_id = :uid OR visibility = 'PUBLIC')
                    """
                ),
                {"did": deck_id, "uid": user_id},
            )
        ).first()
        if owns is None:
            raise LookupError("deck_not_found_or_not_accessible")
    row = (
        await session.execute(
            text(
                """
                INSERT INTO chat_sessions (user_id, deck_id)
                VALUES (:uid, :did)
                RETURNING id
                """
            ),
            {"uid": user_id, "did": deck_id},
        )
    ).one()
    await session.commit()
    return row.id


async def get_session(
    session: AsyncSession, *, session_id: UUID, user_id: UUID
) -> dict | None:
    row = (
        await session.execute(
            text(
                """
                SELECT id, deck_id, total_input_tokens, total_output_tokens,
                       status, created_at, last_message_at
                  FROM chat_sessions
                 WHERE id = :sid AND user_id = :uid
                """
            ),
            {"sid": session_id, "uid": user_id},
        )
    ).first()
    if row is None:
        return None
    return {
        "id": str(row.id),
        "deck_id": str(row.deck_id) if row.deck_id else None,
        "total_input_tokens": int(row.total_input_tokens),
        "total_output_tokens": int(row.total_output_tokens),
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "last_message_at": row.last_message_at.isoformat(),
    }


async def append_message(
    session: AsyncSession,
    *,
    session_id: UUID,
    role: str,
    content: str,
) -> UUID:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO chat_messages (session_id, role, content)
                VALUES (:sid, :role, :content)
                RETURNING id
                """
            ),
            {"sid": session_id, "role": role, "content": content},
        )
    ).one()
    # Rough token estimate: 4 chars/token (OpenAI heuristic). Real tokens
    # come from the LLM response when streaming wires up; this keeps the
    # session input cap responsive in v0.2.
    estimated_tokens = max(1, len(content) // 4)
    if role == "user":
        await session.execute(
            text(
                """
                UPDATE chat_sessions
                   SET total_input_tokens = total_input_tokens + :n,
                       last_message_at = NOW()
                 WHERE id = :sid
                """
            ),
            {"n": estimated_tokens, "sid": session_id},
        )
    else:
        await session.execute(
            text(
                """
                UPDATE chat_sessions
                   SET total_output_tokens = total_output_tokens + :n,
                       last_message_at = NOW()
                 WHERE id = :sid
                """
            ),
            {"n": estimated_tokens, "sid": session_id},
        )
    await session.commit()
    return row.id


async def get_messages(
    session: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
    limit: int = 50,
) -> list[dict]:
    owns = await get_session(session, session_id=session_id, user_id=user_id)
    if owns is None:
        return []
    rows = (
        await session.execute(
            text(
                """
                SELECT id, role, content, created_at
                  FROM chat_messages
                 WHERE session_id = :sid
                 ORDER BY created_at DESC
                 LIMIT :limit
                """
            ),
            {"sid": session_id, "limit": limit},
        )
    ).all()
    return list(reversed([
        {
            "id": str(r.id),
            "role": r.role,
            "content": r.content,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]))


def is_input_capped(total_input_tokens: int) -> bool:
    return total_input_tokens >= _INPUT_TOKEN_CAP


def output_cap() -> int:
    return _OUTPUT_TOKEN_CAP
