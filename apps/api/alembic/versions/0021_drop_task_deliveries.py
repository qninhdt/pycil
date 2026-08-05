"""Drop the question_pool delivery projection, which was never used.

Revision ID: 0021_drop_task_deliveries
Revises: 0020_review_history_ondelete

`async_task_deliveries` and `async_command_receipts.delivery_id` were built for a
task-keyed question supply path that production never took. Measured before dropping:
0 rows in `async_task_deliveries`, 0 receipts with a non-null `delivery_id`, 0
`async_tasks` with `kind='question_pool'` or a `question-pool:` work key, and no
foreign key anywhere pointing at the table. The worker handler that would have
completed such a task described itself as superseded by `prepare_questions`, which is
the path that actually runs.

Reversible: `downgrade` recreates the table, its indexes and the unique constraint
exactly as 0015 defined them, and restores the column and index 0014 added. Nothing
is lost by going back, because there was nothing in it.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0021_drop_task_deliveries"
down_revision = "0020_review_history_ondelete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_async_command_receipts_delivery_id", table_name="async_command_receipts")
    op.drop_column("async_command_receipts", "delivery_id")
    # Indexes and the unique constraint go with the table.
    op.drop_table("async_task_deliveries")


def downgrade() -> None:
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
    op.create_index("ix_async_task_deliveries_owner_id", "async_task_deliveries", ["owner_id"])
    op.create_index(
        "ix_async_task_deliveries_owner_session",
        "async_task_deliveries",
        ["owner_id", "session_id"],
    )
    op.add_column(
        "async_command_receipts",
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_async_command_receipts_delivery_id", "async_command_receipts", ["delivery_id"]
    )
