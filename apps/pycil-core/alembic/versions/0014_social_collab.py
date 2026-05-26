"""Public profiles + deck likes/forks + follows + classrooms + comments (P9).

Revision ID: 0014_social_collab
Revises: 0013_user_definition_stats_and_overrides
"""
from __future__ import annotations

from alembic import op


revision = "0014_social_collab"
down_revision = "0013_user_definition_stats_and_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          CREATE TYPE profile_visibility_enum AS ENUM ('private', 'friends', 'public');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          CREATE TYPE classroom_role_enum AS ENUM ('teacher', 'student');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS username TEXT,
          ADD COLUMN IF NOT EXISTS profile_visibility profile_visibility_enum
            NOT NULL DEFAULT 'private',
          ADD COLUMN IF NOT EXISTS bio_public BOOLEAN NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS streak_public BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower "
        "ON users(LOWER(username)) WHERE username IS NOT NULL"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deck_likes (
          user_id  UUID NOT NULL,
          deck_id  UUID NOT NULL,
          liked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (user_id, deck_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE nodes
          ADD COLUMN IF NOT EXISTS likes_count INT NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS forks_count INT NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS follows (
          follower_id  UUID NOT NULL,
          followee_id  UUID NOT NULL,
          followed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (follower_id, followee_id),
          CHECK (follower_id <> followee_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS follows_followee_lookup ON follows(followee_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS classrooms (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          owner_id     UUID NOT NULL,
          name         TEXT NOT NULL,
          join_code    TEXT UNIQUE NOT NULL,
          created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          max_students SMALLINT NOT NULL DEFAULT 50
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS classroom_members (
          classroom_id UUID NOT NULL,
          user_id      UUID NOT NULL,
          role         classroom_role_enum NOT NULL,
          joined_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (classroom_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS classroom_decks (
          classroom_id UUID NOT NULL,
          deck_id      UUID NOT NULL,
          assigned_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (classroom_id, deck_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS definition_comments (
          id            BIGSERIAL PRIMARY KEY,
          definition_id BIGINT NOT NULL,
          author_id     UUID NOT NULL,
          body          TEXT NOT NULL,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          deleted_at    TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS definition_comments_def "
        "ON definition_comments(definition_id, created_at DESC) "
        "WHERE deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS definition_comments_def")
    op.execute("DROP TABLE IF EXISTS definition_comments")
    op.execute("DROP TABLE IF EXISTS classroom_decks")
    op.execute("DROP TABLE IF EXISTS classroom_members")
    op.execute("DROP TABLE IF EXISTS classrooms")
    op.execute("DROP INDEX IF EXISTS follows_followee_lookup")
    op.execute("DROP TABLE IF EXISTS follows")
    op.execute(
        "ALTER TABLE nodes DROP COLUMN IF EXISTS forks_count, "
        "DROP COLUMN IF EXISTS likes_count"
    )
    op.execute("DROP TABLE IF EXISTS deck_likes")
    op.execute("DROP INDEX IF EXISTS users_username_lower")
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS streak_public, "
        "DROP COLUMN IF EXISTS bio_public, "
        "DROP COLUMN IF EXISTS profile_visibility, "
        "DROP COLUMN IF EXISTS username"
    )
    op.execute("DROP TYPE IF EXISTS classroom_role_enum")
    op.execute("DROP TYPE IF EXISTS profile_visibility_enum")
