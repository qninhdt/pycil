"""Add terms.source enum for provenance (P2 phase 1).

Revision ID: 0009_terms_source
Revises: 0008_llm_response_retry_cache
Create Date: 2026-05-26
"""
from __future__ import annotations

from alembic import op

revision = "0009_terms_source"
down_revision = "0008_llm_response_retry_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE terms
        ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_terms_source ON terms(source)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_terms_source")
    op.execute("ALTER TABLE terms DROP COLUMN IF EXISTS source")
