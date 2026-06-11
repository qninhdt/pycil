"""phase 9 reconciliation: drop auth.js DB tables, add canonical_meaning, token_version, onboarding seed index.

Revision ID: 0003_phase_9_reconciliation
Revises: 0002_deck_terms
Create Date: 2026-05-25

upgrade:
    1. ALTER TABLE definitions ADD COLUMN canonical_meaning TEXT.
    2. Conditional backfill from notes[1] (raw SQL guarded — see Implementation
       step 1 in plan; safe-rerun via WHERE canonical_meaning IS NULL).
    3. ALTER TABLE users ADD COLUMN token_version SMALLINT NOT NULL DEFAULT 0.
    4. CREATE UNIQUE INDEX nodes_user_seed_unique partial on (author_id, name)
       where name in ('Welcome', 'Starter Words') — backs onboarding ON CONFLICT.
    5. DROP TABLE accounts, sessions, verification_token CASCADE (post phase-2).

downgrade:
    Reverses each upgrade step. The auth.js tables are recreated verbatim
    from 0001_init.
"""
from __future__ import annotations

from alembic import op

revision = "0003_phase_9_reconciliation"
down_revision = "0002_deck_terms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE definitions "
        "ADD COLUMN IF NOT EXISTS canonical_meaning TEXT"
    )
    # Conditional backfill: only when notes[1]looks like a meaning (non-empty
    # and rows that have a notes[1] at all). Operators should pre-inspect
    # `SELECT notes[1] FROM definitions ...` per phase-9 plan step 1 before
    # running this migration on a populated DB; on fresh DBs this is a no-op.
    op.execute(
        """
        UPDATE definitions
           SET canonical_meaning = notes[1]
         WHERE canonical_meaning IS NULL
           AND notes IS NOT NULL
           AND array_length(notes, 1) >= 1
        """
    )

    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS token_version SMALLINT NOT NULL DEFAULT 0"
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS nodes_user_seed_unique
        ON nodes (author_id, name)
        WHERE name IN ('Welcome', 'Starter Words')
        """
    )

    # Drop Auth.js v5 DB session tables — phase-2 moved to JWT cookies.
    op.execute("DROP TABLE IF EXISTS verification_token CASCADE")
    op.execute("DROP TABLE IF EXISTS sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS accounts CASCADE")


def downgrade() -> None:
    # Recreate verbatim from 0001_init.py.
    op.execute(
        """
        CREATE TABLE accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            "userId" UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            provider TEXT NOT NULL,
            "providerAccountId" TEXT NOT NULL,
            refresh_token TEXT,
            access_token TEXT,
            expires_at BIGINT,
            id_token TEXT,
            scope TEXT,
            session_state TEXT,
            token_type TEXT,
            UNIQUE(provider, "providerAccountId")
        )
        """
    )
    op.execute('CREATE INDEX idx_accounts_user ON accounts("userId")')

    op.execute(
        """
        CREATE TABLE sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            "sessionToken" TEXT UNIQUE NOT NULL,
            "userId" UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute('CREATE INDEX idx_sessions_user ON sessions("userId")')

    op.execute(
        """
        CREATE TABLE verification_token (
            identifier TEXT NOT NULL,
            token TEXT NOT NULL,
            expires TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (identifier, token)
        )
        """
    )

    op.execute("DROP INDEX IF EXISTS nodes_user_seed_unique")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS token_version")
    op.execute("ALTER TABLE definitions DROP COLUMN IF EXISTS canonical_meaning")
