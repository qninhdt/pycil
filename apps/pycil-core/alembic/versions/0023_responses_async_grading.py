"""Async-grading columns on responses.

Revision ID: 0023_responses_async_grading
Revises: 0022_question_bank_indexes

Supports SSE-streamed LLM grading (phase: async-grading-via-sse):

- ``grade_status`` — 'pending' while the grade_answer worker runs, 'graded'
  once the verdict lands. Sync-graded responses are written 'graded' directly.
- ``session_id`` — the learning session that produced this response, so
  ``apply_async_verdict`` can re-enter the correct session under its lock once
  the async verdict resolves.
- ``elo_applied`` — exactly-once guard: ELO/XP for an async response is applied
  once, set in the same transaction as the user_term_stats UPSERT. A retried or
  double-fired verdict application no-ops.
- ``grade_score`` / ``grade_feedback`` — the verdict's 0..1 credit and
  human-readable feedback, persisted for the apply step + history.

All columns are nullable / defaulted so existing rows and the sync path are
unaffected.
"""
from __future__ import annotations

from alembic import op


revision = "0023_responses_async_grading"
down_revision = "0022_question_bank_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE responses
          ADD COLUMN IF NOT EXISTS grade_status   TEXT NOT NULL DEFAULT 'graded',
          ADD COLUMN IF NOT EXISTS session_id     TEXT,
          ADD COLUMN IF NOT EXISTS elo_applied    BOOLEAN NOT NULL DEFAULT TRUE,
          ADD COLUMN IF NOT EXISTS grade_score    NUMERIC,
          ADD COLUMN IF NOT EXISTS grade_feedback TEXT
        """
    )
    # Pending async grades are looked up by the worker + apply step.
    op.execute(
        "CREATE INDEX IF NOT EXISTS responses_grade_status "
        "ON responses(grade_status) WHERE grade_status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS responses_grade_status")
    op.execute(
        """
        ALTER TABLE responses
          DROP COLUMN IF EXISTS grade_feedback,
          DROP COLUMN IF EXISTS grade_score,
          DROP COLUMN IF EXISTS elo_applied,
          DROP COLUMN IF EXISTS session_id,
          DROP COLUMN IF EXISTS grade_status
        """
    )
