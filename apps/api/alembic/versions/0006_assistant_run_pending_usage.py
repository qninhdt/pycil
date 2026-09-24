"""assistant run pending usage

Adds a column that carried a turn's usage across an approval interrupt, so a
single settlement could cover the whole turn.

Superseded within the same work: billing is now per request, where each request
settles the provider calls it made under a reference generated for that request.
Nothing has to survive between requests, so the column is never read, and the
table it belongs to is dropped by the next revision. It is kept here rather than
deleted because it has already been applied, and removing an applied revision
would leave the chain unresolvable.

Revision ID: 0006_assistant_run_pending_usage
Revises: 0005_credit_period_anchor
Create Date: 2026-09-24 18:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0006_assistant_run_pending_usage'
down_revision: str | None = '0005_credit_period_anchor'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'assistant_runs' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('assistant_runs')]

    if 'pending_usage' not in columns:
        op.add_column(
            'assistant_runs',
            sa.Column('pending_usage', sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'assistant_runs' not in inspector.get_table_names():
        return
    columns = [c['name'] for c in inspector.get_columns('assistant_runs')]
    if 'pending_usage' in columns:
        op.drop_column('assistant_runs', 'pending_usage')
