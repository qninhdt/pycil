"""Durable presentation-only recap for a finished learning session.

Redis owns a session's live state and the namespace is deleted the moment the
session completes, so a reload during or after finishing returned 404 and the recap
was lost. This table is counts only; FSRS effects stay in review_log and
user_sense_stats.

Revision ID: 0018_session_summaries
Revises: 0017_response_grading_projection
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_session_summaries"
down_revision: str | None = "0017_response_grading_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_summaries",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=True),
        sa.Column("senses_admitted", sa.Integer(), nullable=False),
        sa.Column("senses_completed", sa.Integer(), nullable=False),
        sa.Column("senses_exhausted", sa.Integer(), nullable=False),
        sa.Column("answers_total", sa.Integer(), nullable=False),
        sa.Column("answers_correct", sa.Integer(), nullable=False),
        sa.Column("rounds_used", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        # One recap per session per owner: the completion path can run more than
        # once for the same session (a concurrent /next and /answers both reach the
        # completion predicate), and the write must be idempotent.
        sa.UniqueConstraint("user_id", "session_id", name="uq_session_summary"),
    )
    op.create_index(
        op.f("ix_session_summaries_user_id"), "session_summaries", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_session_summaries_user_id"), table_name="session_summaries")
    op.drop_table("session_summaries")
