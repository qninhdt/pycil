"""Add jobs.created_by_user_id for non-term-job ownership checks.

Revision ID: 0005_jobs_created_by_user_id
Revises: 0004_v02_feature_fill
Create Date: 2026-05-26

Closes IDOR on `/jobs/{id}` for translate/tts/regenerate jobs which never
write to user_term_jobs. Column is nullable (existing term jobs continue to
own via user_term_jobs); new non-term enqueues populate it directly.
"""
from __future__ import annotations

from alembic import op

revision = "0005_jobs_created_by_user_id"
down_revision = "0004_v02_feature_fill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS created_by_user_id UUID "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_created_by_user "
        "ON jobs(created_by_user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_jobs_created_by_user")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS created_by_user_id")
