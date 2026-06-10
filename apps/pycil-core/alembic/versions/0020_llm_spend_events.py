"""Persistent LLM spend ledger.

Revision ID: 0020_llm_spend_events
Revises: 0019_user_role_and_ban

One row per non-cached LLM call. `job_id` carries a UNIQUE index so a worker
retry that re-invokes the model dedups to a single row (ON CONFLICT DO NOTHING).
`cost_usd` is the flat per-call estimate today (NOT measured) — surfaced as
"estimated" in the UI.
"""
from __future__ import annotations

from alembic import op


revision = "0020_llm_spend_events"
down_revision = "0019_user_role_and_ban"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_spend_events (
          id            BIGSERIAL PRIMARY KEY,
          user_id       UUID,
          job_id        UUID,
          job_type      TEXT NOT NULL,
          model         TEXT NOT NULL,
          cost_usd      NUMERIC(10,6) NOT NULL,
          input_tokens  INT,
          output_tokens INT,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # Unique on job_id → worker retry's re-invocation dedups to one row.
    # NULL job_ids are distinct in Postgres, so this never blocks job-less rows.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS llm_spend_events_job_id "
        "ON llm_spend_events(job_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS llm_spend_events_created "
        "ON llm_spend_events(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS llm_spend_events_user_created "
        "ON llm_spend_events(user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS llm_spend_events_user_created")
    op.execute("DROP INDEX IF EXISTS llm_spend_events_created")
    op.execute("DROP INDEX IF EXISTS llm_spend_events_job_id")
    op.execute("DROP TABLE IF EXISTS llm_spend_events")
