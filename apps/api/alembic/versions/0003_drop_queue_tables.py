"""drop queue tables

Revision ID: 0003_drop_queue_tables
Revises: 0002_clerk_auth
Create Date: 2026-09-24 05:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0003_drop_queue_tables'
down_revision: str | None = '0002_clerk_auth'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # Drop child tables first due to foreign keys
    if 'job_command_receipts' in tables:
        op.drop_table('job_command_receipts')
    if 'job_interests' in tables:
        op.drop_table('job_interests')
    if 'job_tasks' in tables:
        op.drop_table('job_tasks')


def downgrade() -> None:
    # No restoration required for obsolete queue tables replaced by Redis broker
    pass
