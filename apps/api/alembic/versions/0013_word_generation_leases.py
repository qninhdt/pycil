"""Fence durable word-generation worker leases and retry scheduling.

Revision ID: 0013_word_generation_leases
Revises: 0012_auth_refresh_sessions
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_word_generation_leases"
down_revision = "0012_auth_refresh_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "word_generations",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "word_generations", sa.Column("lease_owner", sa.String(length=128), nullable=True)
    )
    op.add_column("word_generations", sa.Column("lease_token", sa.String(length=64), nullable=True))
    op.add_column(
        "word_generations",
        sa.Column("lease_fence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "word_generations", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "word_generations",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_word_generations_claimable", "word_generations", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    raise NotImplementedError("durable jobs are forward-only")
