"""Job-state lifecycle helper.

Ensures every worker terminates by UPDATEing `jobs.status`+`result`/`error`
exactly once, then PUBLISHing SSE only after `session.commit()` so the
PG-first re-check in `job_stream_service` sees terminal state.

Idempotent: if `jobs.status` is already terminal (retry replay), the UPDATE
returns 0 rows and the caller short-circuits — preventing re-billing on
B2 / Gemini / OpenRouter side effects.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def commit_terminal(
    session: AsyncSession,
    *,
    job_id: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> bool:
    """Atomically transition `jobs.status` → terminal.

    Returns True if this call performed the transition; False if the row was
    already terminal (caller should treat its work as duplicate and skip
    side-effects).
    """
    assert status in ("completed", "failed"), status
    row = (
        await session.execute(
            text(
                """
                UPDATE jobs
                   SET status = :s,
                       result = CAST(:r AS jsonb),
                       error  = :e,
                       updated_at = NOW()
                 WHERE id = :id
                   AND status NOT IN ('completed', 'failed')
                 RETURNING id
                """
            ),
            {
                "s": status,
                "r": json.dumps(result) if result is not None else None,
                "e": error,
                "id": job_id,
            },
        )
    ).first()
    await session.commit()
    return row is not None


async def is_terminal(session: AsyncSession, job_id: str) -> bool:
    """Cheap pre-check before kicking off paid side-effects on retry."""
    row = (
        await session.execute(
            text("SELECT status FROM jobs WHERE id = :id"),
            {"id": job_id},
        )
    ).first()
    return row is not None and row.status in ("completed", "failed")
