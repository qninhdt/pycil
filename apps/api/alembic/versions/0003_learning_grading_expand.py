"""Expand durable learning attempts and pending grading state.

Revision ID: 0003_learning_grading_expand
Revises: 0002_hierarchy_integrity
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_learning_grading_expand"
down_revision: str | None = "0002_hierarchy_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("responses", sa.Column("session_id", sa.String(length=64), nullable=True))
    op.add_column("responses", sa.Column("raw_answer", sa.String(length=10000), nullable=True))
    op.add_column(
        "responses", sa.Column("idempotency_key", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "responses", sa.Column("grading_lease_owner", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "responses",
        sa.Column("grading_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "responses", sa.Column("grading_fence", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_index("ix_responses_session_id", "responses", ["session_id"])
    op.create_index(
        "ix_responses_user_idempotency",
        "responses",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_table(
        "session_sense_attempts",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("sense_id", sa.BigInteger(), nullable=False),
        sa.Column("response_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["response_id"], ["responses.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "session_id", "sense_id", name="uq_session_sense_attempt"),
    )
    op.create_index("ix_session_sense_attempts_user_id", "session_sense_attempts", ["user_id"])


def downgrade() -> None:
    raise RuntimeError("0003 is additive; rollback application code or forward-fix, never drop live schema")
