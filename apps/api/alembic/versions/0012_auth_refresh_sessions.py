"""Persist digest-only rotating refresh-token sessions.

Revision ID: 0012_auth_refresh_sessions
Revises: 0011_word_generation_idempotency
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_auth_refresh_sessions"
down_revision = "0011_word_generation_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_id", sa.UUID(), sa.ForeignKey("refresh_sessions.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index(
        "ix_refresh_sessions_token_digest", "refresh_sessions", ["token_digest"], unique=True
    )
    op.create_index(
        "ix_refresh_sessions_user_active", "refresh_sessions", ["user_id", "revoked_at"]
    )
    op.create_index("ix_refresh_sessions_family", "refresh_sessions", ["family_id"])


def downgrade() -> None:
    raise NotImplementedError("refresh-token storage is forward-only")
