"""init: v1 schema (auth.js + nodes + terms + jobs + learning)

Revision ID: 0001_init
Revises:
Create Date: 2026-05-24

Rollback: `alembic downgrade base` drops every v1 table + enum. Safe before any
production data exists. Post-launch rollbacks must restore from pg_dump.
"""
from __future__ import annotations

from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # --- Enums ---------------------------------------------------------------
    op.execute("CREATE TYPE node_type AS ENUM ('FOLDER', 'DECK')")
    op.execute("CREATE TYPE visibility AS ENUM ('PRIVATE', 'PUBLIC')")
    op.execute(
        "CREATE TYPE term_type AS ENUM "
        "('SINGLE_WORD', 'COMPOUND_WORD', 'FIXED_PHRASE', 'PATTERN_PHRASE')"
    )
    op.execute("CREATE TYPE cefr_level AS ENUM ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')")
    op.execute(
        "CREATE TYPE part_of_speech AS ENUM "
        "('NOUN', 'VERB', 'ADJECTIVE', 'ADVERB', 'PRONOUN', 'PREPOSITION', "
        "'CONJUNCTION', 'INTERJECTION', 'DETERMINER', 'NUMERAL', 'PARTICLE', 'OTHER')"
    )
    op.execute(
        "CREATE TYPE question_type AS ENUM ('MULTIPLE_CHOICE', 'WRITE', 'FILL_IN_BLANK')"
    )

    # --- Auth.js v5 tables (camelCase per @auth/pg-adapter) -----------------
    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT,
            email TEXT UNIQUE NOT NULL,
            "emailVerified" TIMESTAMPTZ,
            image TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
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
    op.execute('CREATE INDEX idx_sessions_user ON sessions("userId")')
    op.execute('CREATE INDEX idx_accounts_user ON accounts("userId")')

    # --- Content: nodes (folders + decks) -----------------------------------
    op.execute(
        """
        CREATE TABLE nodes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            author_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type node_type NOT NULL,
            parent_node_id UUID REFERENCES nodes(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            visibility visibility NOT NULL DEFAULT 'PRIVATE',
            definition_count INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_nodes_author ON nodes(author_id)")
    op.execute("CREATE INDEX idx_nodes_parent ON nodes(parent_node_id)")
    op.execute("CREATE INDEX idx_nodes_type ON nodes(type)")

    op.execute(
        """
        CREATE TABLE folder_attributes (
            node_id UUID PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            subfolder_count INT NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        """
        CREATE TABLE deck_attributes (
            node_id UUID PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
            settings JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )

    # --- Terms + definitions ------------------------------------------------
    op.execute(
        """
        CREATE TABLE terms (
            id BIGSERIAL PRIMARY KEY,
            type term_type NOT NULL DEFAULT 'SINGLE_WORD',
            value TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE definitions (
            id BIGSERIAL PRIMARY KEY,
            term_id BIGINT NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
            frequency INT NOT NULL DEFAULT 0,
            cefr_level cefr_level,
            part_of_speech part_of_speech,
            synonyms TEXT[] NOT NULL DEFAULT '{}',
            antonyms TEXT[] NOT NULL DEFAULT '{}',
            hyponyms TEXT[] NOT NULL DEFAULT '{}',
            hypernyms TEXT[] NOT NULL DEFAULT '{}',
            meronyms TEXT[] NOT NULL DEFAULT '{}',
            holonyms TEXT[] NOT NULL DEFAULT '{}',
            homophones TEXT[] NOT NULL DEFAULT '{}',
            notes TEXT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (term_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_definitions_term ON definitions(term_id)")
    op.execute("CREATE INDEX idx_definitions_cefr ON definitions(cefr_level)")

    op.execute(
        """
        CREATE TABLE definition_paraphrases (
            id BIGSERIAL PRIMARY KEY,
            definition_id BIGINT NOT NULL REFERENCES definitions(id) ON DELETE CASCADE,
            value TEXT NOT NULL,
            cefr_level cefr_level,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_paraphrases_definition ON definition_paraphrases(definition_id)"
    )

    op.execute(
        """
        CREATE TABLE term_example_sentences (
            id BIGSERIAL PRIMARY KEY,
            definition_id BIGINT NOT NULL REFERENCES definitions(id) ON DELETE CASCADE,
            value TEXT NOT NULL,
            cefr_level cefr_level,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_examples_definition ON term_example_sentences(definition_id)"
    )

    # --- Questions ----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE questions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            type question_type NOT NULL,
            definition_id BIGINT NOT NULL REFERENCES definitions(id) ON DELETE CASCADE,
            data JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_questions_definition_type ON questions(definition_id, type)"
    )

    # --- Learning ----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE user_term_stats (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            definition_id BIGINT NOT NULL REFERENCES definitions(id) ON DELETE CASCADE,
            mastery_score INT NOT NULL DEFAULT 1000,
            mastery_level SMALLINT NOT NULL DEFAULT 0,
            last_review_date TIMESTAMPTZ,
            next_review_date TIMESTAMPTZ,
            review_count INT NOT NULL DEFAULT 0,
            interval_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, definition_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_user_term_stats_next_review "
        "ON user_term_stats(user_id, next_review_date)"
    )

    op.execute(
        """
        CREATE TABLE user_nodes (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            is_starred BOOLEAN NOT NULL DEFAULT FALSE,
            is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, node_id)
        )
        """
    )

    # --- Deck ↔ definition junction ----------------------------------------
    op.execute(
        """
        CREATE TABLE deck_definitions (
            deck_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            definition_id BIGINT NOT NULL REFERENCES definitions(id) ON DELETE CASCADE,
            position INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (deck_id, definition_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_deck_definitions_deck ON deck_definitions(deck_id, position)")

    # --- Async jobs --------------------------------------------------------
    op.execute(
        """
        CREATE TABLE jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            result JSONB,
            error TEXT,
            events JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX idx_jobs_status ON jobs(status)")

    # Per-user job ownership for cross-user same-term dedup (phase-3 F10).
    op.execute(
        """
        CREATE TABLE user_term_jobs (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            term_id BIGINT NOT NULL REFERENCES terms(id) ON DELETE CASCADE,
            job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, term_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_user_term_jobs_job ON user_term_jobs(job_id)")


def downgrade() -> None:
    for table in [
        "user_term_jobs",
        "jobs",
        "deck_definitions",
        "user_nodes",
        "user_term_stats",
        "questions",
        "term_example_sentences",
        "definition_paraphrases",
        "definitions",
        "terms",
        "deck_attributes",
        "folder_attributes",
        "nodes",
        "verification_token",
        "sessions",
        "accounts",
        "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    for enum in [
        "question_type",
        "part_of_speech",
        "cefr_level",
        "term_type",
        "visibility",
        "node_type",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
