"""Push subscriptions + study daily goal + activity feed (P4 + P5).

Revision ID: 0017_push_goal_activity
Revises: 0016_compliance_email_infra
"""
from __future__ import annotations

from alembic import op


revision = "0017_push_goal_activity"
down_revision = "0016_compliance_email_infra"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS push_subscriptions (
          id          BIGSERIAL PRIMARY KEY,
          user_id     UUID NOT NULL,
          endpoint    TEXT NOT NULL,
          p256dh      TEXT NOT NULL,
          auth        TEXT NOT NULL,
          user_agent  TEXT,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          last_used_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS push_subscriptions_endpoint "
        "ON push_subscriptions(user_id, endpoint)"
    )
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS daily_goal SMALLINT NOT NULL DEFAULT 20,
          ADD COLUMN IF NOT EXISTS reminder_hour SMALLINT
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_events (
          id         BIGSERIAL PRIMARY KEY,
          user_id    UUID NOT NULL,
          kind       TEXT NOT NULL,
          payload    JSONB NOT NULL DEFAULT '{}',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS activity_events_user "
        "ON activity_events(user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS activity_events_user")
    op.execute("DROP TABLE IF EXISTS activity_events")
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS reminder_hour, "
        "DROP COLUMN IF EXISTS daily_goal"
    )
    op.execute("DROP INDEX IF EXISTS push_subscriptions_endpoint")
    op.execute("DROP TABLE IF EXISTS push_subscriptions")
