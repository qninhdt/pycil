"""Add durable assistant records and migration-owned LangGraph checkpoint tables.

Revision ID: 0008_assistant_agent
Revises: 0007_response_mastery
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_assistant_agent"
down_revision: str | None = "0007_response_mastery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    run_status = sa.Enum(
        "PENDING", "RUNNING", "INTERRUPTED", "SUCCEEDED", "FAILED", "CANCELLED", name="runstatus"
    )
    action_status = sa.Enum(
        "PENDING",
        "APPROVED",
        "REJECTED",
        "EXECUTING",
        "SUCCEEDED",
        "FAILED",
        "EXPIRED",
        "INVALIDATED",
        name="actionstatus",
    )
    op.create_table(
        "assistant_threads",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("owner_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="New conversation"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("retention_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_assistant_threads_owner_id", "assistant_threads", ["owner_id"])
    op.create_table(
        "assistant_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("thread_id", sa.UUID(), sa.ForeignKey("assistant_threads.id"), nullable=False),
        sa.Column("owner_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_message_id", sa.UUID(), nullable=False),
        sa.Column("status", run_status, nullable=False, server_default="PENDING"),
        sa.Column("event_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint(
            "owner_id", "client_message_id", name="uq_assistant_runs_owner_message"
        ),
    )
    op.create_index("ix_assistant_runs_thread_id", "assistant_runs", ["thread_id"])
    op.create_index("ix_assistant_runs_owner_id", "assistant_runs", ["owner_id"])
    op.create_index("ix_assistant_runs_active_thread", "assistant_runs", ["thread_id", "status"])
    op.create_table(
        "assistant_run_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("run_id", sa.UUID(), sa.ForeignKey("assistant_runs.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("sanitized_payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("run_id", "sequence", name="uq_assistant_events_run_sequence"),
    )
    op.create_index("ix_assistant_run_events_run_id", "assistant_run_events", ["run_id"])
    op.create_table(
        "assistant_actions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("run_id", sa.UUID(), sa.ForeignKey("assistant_runs.id"), nullable=False),
        sa.Column("owner_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("args_digest", sa.String(64), nullable=False),
        sa.Column("canonical_args", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("checkpoint_version", sa.String(255)),
        sa.Column("resource_generation", sa.Integer()),
        sa.Column("status", action_status, nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.dialects.postgresql.JSONB()),
        sa.Column("correlation_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_assistant_actions_run_id", "assistant_actions", ["run_id"])
    op.create_index("ix_assistant_actions_owner_id", "assistant_actions", ["owner_id"])
    op.create_index(
        "ix_assistant_actions_pending_expiry", "assistant_actions", ["status", "expires_at"]
    )
    op.create_table(
        "assistant_action_audit",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("action_id", sa.UUID(), sa.ForeignKey("assistant_actions.id")),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("sanitized_digest", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.UUID(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_assistant_action_audit_action_id", "assistant_action_audit", ["action_id"])
    op.create_index("ix_assistant_action_audit_actor_id", "assistant_action_audit", ["actor_id"])
    for statement in (
        "CREATE TABLE checkpoint_migrations (v INTEGER PRIMARY KEY)",
        (
            "CREATE TABLE checkpoints (thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL "
            "DEFAULT '', checkpoint_id TEXT NOT NULL, parent_checkpoint_id TEXT, type TEXT, "
            "checkpoint JSONB NOT NULL, metadata JSONB NOT NULL DEFAULT '{}', "
            "PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))"
        ),
        (
            "CREATE TABLE checkpoint_blobs (thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL "
            "DEFAULT '', channel TEXT NOT NULL, version TEXT NOT NULL, type TEXT NOT NULL, "
            "blob BYTEA, PRIMARY KEY (thread_id, checkpoint_ns, channel, version))"
        ),
        (
            "CREATE TABLE checkpoint_writes (thread_id TEXT NOT NULL, checkpoint_ns TEXT NOT NULL "
            "DEFAULT '', checkpoint_id TEXT NOT NULL, task_id TEXT NOT NULL, idx INTEGER NOT NULL, "
            "channel TEXT NOT NULL, type TEXT, blob BYTEA NOT NULL, task_path TEXT NOT NULL "
            "DEFAULT '', PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx))"
        ),
        "CREATE INDEX checkpoints_thread_id_idx ON checkpoints(thread_id)",
        "CREATE INDEX checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id)",
        "CREATE INDEX checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id)",
    ):
        op.execute(statement)
    op.bulk_insert(
        sa.table("checkpoint_migrations", sa.column("v", sa.Integer())),
        [{"v": v} for v in range(10)],
    )


def downgrade() -> None:
    raise RuntimeError(
        "0008 is additive and contains assistant audit data; "
        "forward-fix rather than dropping live records"
    )
