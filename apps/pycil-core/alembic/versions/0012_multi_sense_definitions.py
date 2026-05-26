"""Multi-sense definitions schema (P8 phase 1).

Revision ID: 0012_multi_sense_definitions
Revises: 0011_feature_flags

DESTRUCTIVE: drops UNIQUE(term_id) constraint on definitions; replaces it
with UNIQUE(term_id, sense_index). Existing rows backfilled with
sense_index=0, is_primary=true. UI / read-paths must filter on is_primary
during the rollout window before consuming the full sense list.
"""
from __future__ import annotations

from alembic import op


revision = "0012_multi_sense_definitions"
down_revision = "0011_feature_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE definitions
          ADD COLUMN IF NOT EXISTS sense_index SMALLINT NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS disambiguator TEXT,
          ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT true
        """
    )
    op.execute(
        "ALTER TABLE definitions DROP CONSTRAINT IF EXISTS definitions_term_id_key"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
             WHERE conname = 'definitions_term_sense_unique'
          ) THEN
            ALTER TABLE definitions
              ADD CONSTRAINT definitions_term_sense_unique
              UNIQUE (term_id, sense_index);
          END IF;
        END$$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS definitions_term_primary "
        "ON definitions (term_id) WHERE is_primary"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS definitions_term_primary")
    op.execute(
        "ALTER TABLE definitions DROP CONSTRAINT IF EXISTS definitions_term_sense_unique"
    )
    op.execute("ALTER TABLE definitions DROP COLUMN IF EXISTS is_primary")
    op.execute("ALTER TABLE definitions DROP COLUMN IF EXISTS disambiguator")
    op.execute("ALTER TABLE definitions DROP COLUMN IF EXISTS sense_index")
