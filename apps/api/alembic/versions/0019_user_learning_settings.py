"""Move session-shape settings from per-deck JSONB to a per-user row.

Session shape is a property of the learner, not of a deck. Holding it per deck
meant the same person got different session lengths depending on which deck they
opened, and a client wanting to show "your settings" had to walk the whole node
tree to find every deck first.

``deck_attributes.settings`` is left in place and simply stops being read. Its
values are not migrated: a learner with three decks configured differently has no
single correct global value, and there is nothing to preserve anyway because the
keys the planner read were only ever written by a recently corrected endpoint.

Revision ID: 0019_user_learning_settings
Revises: 0018_session_summaries
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_user_learning_settings"
down_revision: str | None = "0018_session_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_learning_settings",
        # The user is the primary key: one row per learner, or none at all. An
        # absent row means "policy defaults", so signing up needs no write and a
        # learner who never opens Settings has nothing stored.
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_words_per_session", sa.Integer(), nullable=False),
        sa.Column("max_questions_per_round", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
        # Bounds enforced in the database as well as in the DTO. The planner
        # divides by these, so a zero or a negative value reaching the row from
        # any future writer would produce a session with no work in it.
        sa.CheckConstraint(
            "target_words_per_session BETWEEN 1 AND 100",
            name="ck_user_learning_settings_target_words",
        ),
        sa.CheckConstraint(
            "max_questions_per_round BETWEEN 1 AND 100",
            name="ck_user_learning_settings_max_per_round",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_learning_settings")
