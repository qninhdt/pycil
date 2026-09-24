"""drop assistant runs

Conversation state is owned by the LangGraph checkpointer, and the active-turn
bound is a Redis lease, so the run table held nothing that is not now owned
elsewhere. Dropping it removes the second state machine rather than leaving it to
drift out of step with the graph.

The checkpointer's own tables are created by ``AsyncPostgresSaver.setup()`` and are
not managed here.

Revision ID: 0007_drop_assistant_runs
Revises: 0006_assistant_run_pending_usage
Create Date: 2026-09-24 19:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0007_drop_assistant_runs'
down_revision: str | None = '0006_assistant_run_pending_usage'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'assistant_runs' in inspector.get_table_names():
        op.drop_table('assistant_runs')


def downgrade() -> None:
    # Recreated in its final shape so a rollback leaves a usable table rather than
    # a missing one. The rows it held are not recoverable, which is the point of
    # the drop: nothing in them is a source of truth.
    op.create_table(
        'assistant_runs',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('thread_id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('client_message_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_code', sa.String(length=80), nullable=True),
        sa.Column('pending_usage', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['thread_id'], ['assistant_threads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
