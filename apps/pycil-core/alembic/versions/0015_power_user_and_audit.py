"""Power user features: term notes (P10 phase 2) + admin audit log (P12 phase 2).

Revision ID: 0015_power_user_and_audit
Revises: 0014_social_collab
"""
from __future__ import annotations

from alembic import op

revision = "0015_power_user_and_audit"
down_revision = "0014_social_collab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS term_notes (
          user_id    UUID NOT NULL,
          term_id    BIGINT NOT NULL,
          body       TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (user_id, term_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_actions (
          id              BIGSERIAL PRIMARY KEY,
          actor_user_id   UUID NOT NULL,
          target_user_id  UUID,
          action          TEXT NOT NULL,
          metadata        JSONB NOT NULL DEFAULT '{}',
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          ip_address      INET,
          user_agent      TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS admin_actions_target "
        "ON admin_actions(target_user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS admin_actions_actor "
        "ON admin_actions(actor_user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS admin_actions_actor")
    op.execute("DROP INDEX IF EXISTS admin_actions_target")
    op.execute("DROP TABLE IF EXISTS admin_actions")
    op.execute("DROP TABLE IF EXISTS term_notes")
