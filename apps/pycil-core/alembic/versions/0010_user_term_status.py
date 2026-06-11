"""Suspend/bury/leech handling for user_term_stats (P3 phase 3).

Revision ID: 0010_user_term_status
Revises: 0009_terms_source
"""
from __future__ import annotations

from alembic import op

revision = "0010_user_term_status"
down_revision = "0009_terms_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          CREATE TYPE user_term_status AS ENUM ('active', 'suspended', 'buried');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE user_term_stats
          ADD COLUMN IF NOT EXISTS status user_term_status NOT NULL DEFAULT 'active',
          ADD COLUMN IF NOT EXISTS buried_until DATE,
          ADD COLUMN IF NOT EXISTS lapse_count INT NOT NULL DEFAULT 0
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_term_stats DROP COLUMN IF EXISTS lapse_count, "
        "DROP COLUMN IF EXISTS buried_until, DROP COLUMN IF EXISTS status"
    )
    op.execute("DROP TYPE IF EXISTS user_term_status")
