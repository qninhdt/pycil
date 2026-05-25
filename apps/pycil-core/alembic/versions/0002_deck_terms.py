"""add deck_terms junction (deck → term, pre-enrichment)

Revision ID: 0002_deck_terms
Revises: 0001_init
Create Date: 2026-05-24

Phase 2 needs to link a deck to a term before any definition exists. Once
phase 3 generates a definition for a term, the worker will translate matching
deck_terms rows into deck_definitions(deck_id, definition_id, position) rows.

Rollback: drop deck_terms table.
"""
from __future__ import annotations

from alembic import op

revision = "0002_deck_terms"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE deck_terms (
            deck_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            term_id BIGINT NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
            position INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (deck_id, term_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_deck_terms_term ON deck_terms(term_id)")
    op.execute("CREATE INDEX idx_deck_terms_deck_pos ON deck_terms(deck_id, position)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deck_terms CASCADE")
