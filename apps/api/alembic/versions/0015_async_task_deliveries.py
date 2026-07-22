"""Add durable private session deliveries for shared async tasks.

Revision ID: 0015_async_task_deliveries
Revises: 0014_global_async_tasks
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015_async_task_deliveries"
down_revision = "0014_global_async_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "async_task_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("async_tasks.id"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("sense_id", sa.Integer(), nullable=False),
        sa.Column("question_format", sa.String(length=80), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("task_id", "session_id", name="uq_task_delivery_session"),
    )
    op.create_index("ix_async_task_deliveries_task_id", "async_task_deliveries", ["task_id"])
    op.create_index(
        "ix_async_task_deliveries_owner_id", "async_task_deliveries", ["owner_id"]
    )
    op.create_index(
        "ix_async_task_deliveries_owner_session",
        "async_task_deliveries",
        ["owner_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_table("async_task_deliveries")
