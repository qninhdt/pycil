"""Feature flags table (P6 phase 2).

Revision ID: 0011_feature_flags
Revises: 0010_user_term_status
"""
from __future__ import annotations

from alembic import op

revision = "0011_feature_flags"
down_revision = "0010_user_term_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_flags (
          name TEXT PRIMARY KEY,
          rollout_percentage SMALLINT NOT NULL DEFAULT 0
            CHECK (rollout_percentage BETWEEN 0 AND 100),
          enabled_user_ids UUID[] NOT NULL DEFAULT '{}',
          payload JSONB NOT NULL DEFAULT '{}',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_by UUID
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feature_flags")
