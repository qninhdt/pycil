"""Add subscriptions.last_event_at + last_event_id for webhook ordering.

Revision ID: 0006_subscription_event_ordering
Revises: 0005_jobs_created_by_user_id
Create Date: 2026-05-26

Stripe doesn't guarantee delivery order. With both columns, ON CONFLICT
guards updates by `(last_event_at, last_event_id) > existing` lexicographic
tiebreak — handles same-second collisions deterministically.
"""
from __future__ import annotations

from alembic import op

revision = "0006_subscription_event_ordering"
down_revision = "0005_jobs_created_by_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subscriptions "
        "ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ "
        "NOT NULL DEFAULT '1970-01-01T00:00:00Z'"
    )
    op.execute(
        "ALTER TABLE subscriptions "
        "ADD COLUMN IF NOT EXISTS last_event_id TEXT NOT NULL DEFAULT ''"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS last_event_id")
    op.execute("ALTER TABLE subscriptions DROP COLUMN IF EXISTS last_event_at")
