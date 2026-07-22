"""Add generic async tasks, interests, events, outbox, and command receipts.

Revision ID: 0014_global_async_tasks
Revises: 0013_word_generation_leases
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0014_global_async_tasks"
down_revision = "0013_word_generation_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "async_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("work_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_fence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_async_tasks_claimable", "async_tasks", ["status", "next_attempt_at"])
    op.create_index(
        "uq_async_tasks_active_work",
        "async_tasks",
        ["kind", "work_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'succeeded')"),
    )
    op.create_table(
        "async_task_interests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("async_tasks.id"),
            nullable=False,
        ),
        sa.Column(
            "requester_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "task_id", "requester_id", "provenance", name="uq_task_interest_provenance"
        ),
    )
    op.create_index(
        "ix_async_task_interests_requester", "async_task_interests", ["requester_id", "expires_at"]
    )
    op.create_index("ix_async_task_interests_task_id", "async_task_interests", ["task_id"])
    op.create_table(
        "async_task_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("async_tasks.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "schema_name", sa.String(length=40), nullable=False, server_default="async-task.v1"
        ),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("task_id", "version", name="uq_task_event_version"),
    )
    op.create_index("ix_async_task_events_task_id", "async_task_events", ["task_id"])
    op.create_table(
        "async_task_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("async_task_events.id"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=160), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("event_id", name="uq_async_task_outbox_event"),
    )
    op.create_index(
        "ix_async_task_outbox_claimable", "async_task_outbox", ["status", "next_attempt_at"]
    )
    op.create_table(
        "async_command_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "requester_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("command_kind", sa.String(length=80), nullable=False),
        sa.Column("command_id", sa.String(length=128), nullable=False),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("async_tasks.id"),
            nullable=False,
        ),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "requester_id", "command_kind", "command_id", name="uq_async_command_receipt"
        ),
    )
    op.create_index(
        "ix_async_command_receipts_requester", "async_command_receipts", ["requester_id"]
    )
    op.create_index("ix_async_command_receipts_task_id", "async_command_receipts", ["task_id"])
    op.create_index(
        "ix_async_command_receipts_delivery_id", "async_command_receipts", ["delivery_id"]
    )


def downgrade() -> None:
    op.drop_table("async_command_receipts")
    op.drop_table("async_task_outbox")
    op.drop_table("async_task_events")
    op.drop_table("async_task_interests")
    op.drop_table("async_tasks")
