"""User definition stats + overrides (P8 phases 4 + 7).

Revision ID: 0013_user_definition_stats_and_overrides
Revises: 0012_multi_sense_definitions
"""
from __future__ import annotations

from alembic import op

revision = "0013_user_definition_stats_and_overrides"
down_revision = "0012_multi_sense_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_definition_stats (
          user_id        UUID NOT NULL,
          definition_id  BIGINT NOT NULL,
          elo            INT NOT NULL DEFAULT 800,
          total_seen     INT NOT NULL DEFAULT 0,
          total_correct  INT NOT NULL DEFAULT 0,
          last_seen_at   TIMESTAMPTZ,
          status         TEXT NOT NULL DEFAULT 'active',
          buried_until   DATE,
          lapse_count    INT NOT NULL DEFAULT 0,
          PRIMARY KEY (user_id, definition_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS user_definition_stats_user "
        "ON user_definition_stats(user_id, last_seen_at)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS definition_overrides (
          user_id       UUID NOT NULL,
          term_id       BIGINT NOT NULL,
          payload       JSONB NOT NULL,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (user_id, term_id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS definition_overrides")
    op.execute("DROP INDEX IF EXISTS user_definition_stats_user")
    op.execute("DROP TABLE IF EXISTS user_definition_stats")
