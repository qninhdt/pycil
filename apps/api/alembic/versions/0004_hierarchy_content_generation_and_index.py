"""hierarchy content generation and target_node_id index

Revision ID: 0004_hierarchy_cache
Revises: 0003_drop_queue_tables
Create Date: 2026-09-24 05:15:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0004_hierarchy_cache'
down_revision: str | None = '0003_drop_queue_tables'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    node_cols = [c['name'] for c in inspector.get_columns('nodes')]

    if 'content_generation' not in node_cols:
        op.add_column(
            'nodes',
            sa.Column('content_generation', sa.Integer(), server_default='0', nullable=False),
        )

    indexes = [idx['name'] for idx in inspector.get_indexes('nodes')]
    if 'ix_nodes_target_node_id' not in indexes:
        op.create_index(
            op.f('ix_nodes_target_node_id'),
            'nodes',
            ['target_node_id'],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_nodes_target_node_id'), table_name='nodes')
    op.drop_column('nodes', 'content_generation')
