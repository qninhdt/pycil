"""v0.2 feature fill: gamification, notifications, search, write/fill questions,
shortcuts, public decks, translation/tts, chat, test mode, subscriptions.

Revision ID: 0004_v02_feature_fill
Revises: 0003_phase_9_reconciliation
Create Date: 2026-05-25

upgrade: additive only. Every column nullable or default-valued. Every new
table fully isolated. ENUM extensions and GIN-CONCURRENTLY indexes use
autocommit_block() per Postgres requirements.

downgrade: best-effort dev-only. Reverses table/column adds. ENUM values
added by upgrade survive downgrade — Postgres has no clean ALTER TYPE DROP
VALUE, and IF NOT EXISTS makes round-trip schema-clean by construction.
"""
from __future__ import annotations

from alembic import op

revision = "0004_v02_feature_fill"
down_revision = "0003_phase_9_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- pg_trgm extension (required for GIN trigram indexes) ----------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- users: gamification + profile + soft-delete + stripe ----------------
    op.execute(
        """
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS image_url TEXT,
            ADD COLUMN IF NOT EXISTS streak_days INT NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS last_session_date DATE,
            ADD COLUMN IF NOT EXISTS xp_total INT NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS level SMALLINT NOT NULL DEFAULT 1,
            ADD COLUMN IF NOT EXISTS badges JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS league_rank SMALLINT NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS locale TEXT NOT NULL DEFAULT 'en',
            ADD COLUMN IF NOT EXISTS bio TEXT,
            ADD COLUMN IF NOT EXISTS study_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_stripe_customer_id_unique "
        "ON users(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_deleted_at "
        "ON users(deleted_at) WHERE deleted_at IS NOT NULL"
    )

    # --- notifications -------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            read_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread "
        "ON notifications(user_id, read_at NULLS FIRST, created_at DESC)"
    )

    # --- definitions: tags, translation, tts_url -----------------------------
    op.execute(
        """
        ALTER TABLE definitions
            ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS translation JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS tts_url JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )

    # --- questions: per-question ELO + variant seed --------------------------
    op.execute(
        """
        ALTER TABLE questions
            ADD COLUMN IF NOT EXISTS elo INT NOT NULL DEFAULT 1000,
            ADD COLUMN IF NOT EXISTS variant_seed INT
        """
    )

    # --- responses (NEW table — phase 7 grading audit + phase 8 calibration) -
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS responses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            is_correct BOOL NOT NULL,
            user_answer TEXT,
            grade_reason TEXT,
            grade_confidence NUMERIC,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_responses_user_created "
        "ON responses(user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_responses_question_created "
        "ON responses(question_id, created_at DESC)"
    )

    # --- nodes: SHORTCUT type + target_node_id -------------------------------
    # ENUM addition must run outside a transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE node_type ADD VALUE IF NOT EXISTS 'SHORTCUT'")

    op.execute(
        """
        ALTER TABLE nodes
            ADD COLUMN IF NOT EXISTS target_node_id UUID
                REFERENCES nodes(id) ON DELETE SET NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_nodes_target ON nodes(target_node_id) "
        "WHERE target_node_id IS NOT NULL"
    )

    # --- deck_clones ---------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deck_clones (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_deck_id UUID REFERENCES nodes(id) ON DELETE SET NULL,
            cloned_deck_id UUID REFERENCES nodes(id) ON DELETE SET NULL,
            cloned_by_user UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cloned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deck_clones_source ON deck_clones(source_deck_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_deck_clones_cloner ON deck_clones(cloned_by_user)"
    )

    # --- chat_sessions + chat_messages (phase 11) ----------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            deck_id UUID REFERENCES nodes(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            total_input_tokens INT NOT NULL DEFAULT 0,
            total_output_tokens INT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_recent "
        "ON chat_sessions(user_id, last_message_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session "
        "ON chat_messages(session_id, created_at)"
    )

    # --- test_runs + test_run_items (phase 12) -------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS test_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            deck_id UUID REFERENCES nodes(id) ON DELETE SET NULL,
            question_count SMALLINT NOT NULL,
            correct_count SMALLINT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            score_pct NUMERIC
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_test_runs_user_started "
        "ON test_runs(user_id, started_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS test_run_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
            question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            answered_at TIMESTAMPTZ,
            user_answer TEXT,
            is_correct BOOL,
            position SMALLINT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_test_run_items_run "
        "ON test_run_items(run_id, position)"
    )

    # --- subscriptions + stripe_webhook_events (phase 16) --------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            tier TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'pro')),
            stripe_subscription_id TEXT UNIQUE,
            current_period_end TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS stripe_webhook_events (
            event_id TEXT PRIMARY KEY,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # --- node_share_links (phase 6) ------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS node_share_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            token TEXT UNIQUE NOT NULL,
            created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revoked_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_share_links_node "
        "ON node_share_links(node_id, revoked_at)"
    )

    # --- user_term_jobs: SSE replay + retry idempotency (phase 8) ------------
    op.execute(
        """
        ALTER TABLE user_term_jobs
            ADD COLUMN IF NOT EXISTS last_event JSONB,
            ADD COLUMN IF NOT EXISTS last_llm_response JSONB
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_term_jobs_user "
        "ON user_term_jobs(user_id)"
    )

    # --- search GIN trigram indexes (phase 5) --------------------------------
    # CONCURRENTLY requires autocommit; IF NOT EXISTS makes re-run safe.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS terms_value_trgm "
            "ON terms USING gin (value gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS nodes_name_trgm "
            "ON nodes USING gin (name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS definitions_canonical_trgm "
            "ON definitions USING gin (canonical_meaning gin_trgm_ops)"
        )

    # --- partial fast-path index for due reviews (phase 8/learn) -------------
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_term_stats_due "
        "ON user_term_stats(user_id, next_review_date) "
        "WHERE next_review_date IS NOT NULL"
    )


def downgrade() -> None:
    # GIN indexes (CONCURRENTLY for symmetry with upgrade).
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS definitions_canonical_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS nodes_name_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS terms_value_trgm")

    op.execute("DROP INDEX IF EXISTS idx_user_term_stats_due")
    op.execute("DROP INDEX IF EXISTS idx_user_term_jobs_user")
    op.execute("ALTER TABLE user_term_jobs DROP COLUMN IF EXISTS last_llm_response")
    op.execute("ALTER TABLE user_term_jobs DROP COLUMN IF EXISTS last_event")

    # Tables (most-isolated first).
    for table in [
        "node_share_links",
        "stripe_webhook_events",
        "subscriptions",
        "test_run_items",
        "test_runs",
        "chat_messages",
        "chat_sessions",
        "deck_clones",
        "responses",
        "notifications",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Column drops.
    op.execute("DROP INDEX IF EXISTS idx_nodes_target")
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS target_node_id")

    op.execute(
        """
        ALTER TABLE questions
            DROP COLUMN IF EXISTS variant_seed,
            DROP COLUMN IF EXISTS elo
        """
    )

    op.execute(
        """
        ALTER TABLE definitions
            DROP COLUMN IF EXISTS tts_url,
            DROP COLUMN IF EXISTS translation,
            DROP COLUMN IF EXISTS tags
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_users_deleted_at")
    op.execute("DROP INDEX IF EXISTS users_stripe_customer_id_unique")
    op.execute(
        """
        ALTER TABLE users
            DROP COLUMN IF EXISTS stripe_customer_id,
            DROP COLUMN IF EXISTS deleted_at,
            DROP COLUMN IF EXISTS study_settings,
            DROP COLUMN IF EXISTS bio,
            DROP COLUMN IF EXISTS locale,
            DROP COLUMN IF EXISTS league_rank,
            DROP COLUMN IF EXISTS badges,
            DROP COLUMN IF EXISTS level,
            DROP COLUMN IF EXISTS xp_total,
            DROP COLUMN IF EXISTS last_session_date,
            DROP COLUMN IF EXISTS streak_days,
            DROP COLUMN IF EXISTS image_url
        """
    )

    # Note: ENUM value 'SHORTCUT' added by upgrade is NOT removed here.
    # Postgres lacks ALTER TYPE DROP VALUE; round-trip schema-clean is preserved
    # because upgrade uses IF NOT EXISTS.
