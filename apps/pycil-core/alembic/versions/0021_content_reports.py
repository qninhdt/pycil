"""Content reports moderation pipeline + nodes.deleted_at for admin soft-delete.

Revision ID: 0021_content_reports
Revises: 0020_llm_spend_events

- `nodes.deleted_at TIMESTAMPTZ NULL`: enables reversible admin soft-delete of
  decks (red-team F9 — the existing `delete_node` is a HARD owner-gated DELETE).
- `content_reports`: user-submitted moderation reports. Two typed FK columns
  (`node_id` / `comment_id`) with a CHECK that exactly one is set (Validation
  V3) — no TEXT content_id, no runtime cast, no injection surface.
"""
from __future__ import annotations

from alembic import op


revision = "0021_content_reports"
down_revision = "0020_llm_spend_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS content_reports (
          id               BIGSERIAL PRIMARY KEY,
          reporter_user_id UUID NOT NULL,
          content_type     TEXT NOT NULL,
          node_id          UUID,
          comment_id       BIGINT,
          reason           TEXT NOT NULL,
          details          TEXT,
          status           TEXT NOT NULL DEFAULT 'pending',
          target_owner_id  UUID,
          target_snapshot  JSONB,
          resolved_by      UUID,
          resolved_at      TIMESTAMPTZ,
          resolution       TEXT,
          created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT content_reports_exactly_one_target CHECK (
            (node_id IS NOT NULL)::int + (comment_id IS NOT NULL)::int = 1
          )
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS content_reports_status "
        "ON content_reports(status, created_at DESC)"
    )
    # One pending report per (reporter, target). COALESCE both typed FKs to text
    # so the partial-unique key covers either content type.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS content_reports_pending_dedup "
        "ON content_reports("
        "  reporter_user_id, content_type, "
        "  COALESCE(node_id::text, comment_id::text)"
        ") WHERE status = 'pending'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS content_reports_target_owner "
        "ON content_reports(target_owner_id) WHERE target_owner_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS content_reports_target_owner")
    op.execute("DROP INDEX IF EXISTS content_reports_pending_dedup")
    op.execute("DROP INDEX IF EXISTS content_reports_status")
    op.execute("DROP TABLE IF EXISTS content_reports")
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS deleted_at")
