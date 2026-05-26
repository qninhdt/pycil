"""Backup rehearsal table (P6 phase 6).

Revision ID: 0018_backup_rehearsals
Revises: 0017_push_goal_activity
"""
from __future__ import annotations

from alembic import op


revision = "0018_backup_rehearsals"
down_revision = "0017_push_goal_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS backup_rehearsals (
          backup_id     TEXT PRIMARY KEY,
          rehearsed_at  TIMESTAMPTZ NOT NULL,
          status        TEXT NOT NULL,
          rows_users    INT,
          rows_decks    INT,
          rows_terms    INT,
          error         TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS backup_rehearsals_status "
        "ON backup_rehearsals(status, rehearsed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS backup_rehearsals_status")
    op.execute("DROP TABLE IF EXISTS backup_rehearsals")
