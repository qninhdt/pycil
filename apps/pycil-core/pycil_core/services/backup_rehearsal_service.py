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

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

_log = logging.getLogger(__name__)

from shared.db import BackupRehearsal

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
    stmt = insert(BackupRehearsal).values(
        backup_id=backup_id,
        rehearsed_at=rehearsed_at,
        status=status,
        rows_users=rows_users,
        rows_decks=rows_decks,
        rows_terms=rows_terms,
        error=error,
    )
    await session.exec(
        stmt.on_conflict_do_update(
            index_elements=[BackupRehearsal.backup_id],
            set_={
                "rehearsed_at": stmt.excluded.rehearsed_at,
                "status": stmt.excluded.status,
                "rows_users": stmt.excluded.rows_users,
                "rows_decks": stmt.excluded.rows_decks,
                "rows_terms": stmt.excluded.rows_terms,
                "error": stmt.excluded.error,
            },
        )
    )


async def latest(session: AsyncSession) -> dict | None:
    row = (
        await session.exec(
            select(
                BackupRehearsal.backup_id,
                BackupRehearsal.rehearsed_at,
                BackupRehearsal.status,
                BackupRehearsal.error,
            )
            .order_by(BackupRehearsal.rehearsed_at.desc())
            .limit(1)
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
