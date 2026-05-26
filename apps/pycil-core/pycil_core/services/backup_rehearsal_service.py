"""Backup rehearsal cron (P6 phase 6).

Daily job: trigger pg_dump → S3-compatible storage; weekly: pull a
random recent dump, restore into a temp DB, run a smoke query that
counts users + decks + terms, and report SUCCESS / FAIL via webhook.

This module is a thin wrapper — the actual pg_dump/restore commands run
in the deploy host's cron, not here. We track outcomes in the
backup_rehearsals table for visibility.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)

OutcomeStatus = Literal["success", "failure"]


async def record_rehearsal(
    session: AsyncSession,
    *,
    backup_id: str,
    rehearsed_at: datetime,
    status: OutcomeStatus,
    rows_users: int | None = None,
    rows_decks: int | None = None,
    rows_terms: int | None = None,
    error: str | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO backup_rehearsals
              (backup_id, rehearsed_at, status,
               rows_users, rows_decks, rows_terms, error)
            VALUES (:b, :t, :s, :u, :d, :tr, :e)
            ON CONFLICT (backup_id) DO UPDATE
              SET rehearsed_at = EXCLUDED.rehearsed_at,
                  status = EXCLUDED.status,
                  rows_users = EXCLUDED.rows_users,
                  rows_decks = EXCLUDED.rows_decks,
                  rows_terms = EXCLUDED.rows_terms,
                  error = EXCLUDED.error
            """
        ),
        {
            "b": backup_id,
            "t": rehearsed_at,
            "s": status,
            "u": rows_users,
            "d": rows_decks,
            "tr": rows_terms,
            "e": error,
        },
    )


async def latest(session: AsyncSession) -> dict | None:
    row = (
        await session.execute(
            text(
                "SELECT backup_id, rehearsed_at, status, error "
                "FROM backup_rehearsals ORDER BY rehearsed_at DESC LIMIT 1"
            )
        )
    ).first()
    if not row:
        return None
    return {
        "backup_id": row.backup_id,
        "rehearsed_at": row.rehearsed_at,
        "status": row.status,
        "error": row.error,
    }
