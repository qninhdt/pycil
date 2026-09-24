"""clerk auth migration

Revision ID: 0002_clerk_auth
Revises: 0001_baseline
Create Date: 2026-09-24 04:47:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0002_clerk_auth'
down_revision: str | None = '0001_baseline'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add clerk_id column to users table
    op.add_column('users', sa.Column('clerk_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_users_clerk_id'), 'users', ['clerk_id'], unique=True)

    # 2. Drop legacy auth tables if they exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'refresh_sessions' in tables:
        op.drop_table('refresh_sessions')
    if 'external_identities' in tables:
        op.drop_table('external_identities')

    # 3. Drop token_version column from users if it exists
    user_cols = [c['name'] for c in inspector.get_columns('users')]
    if 'token_version' in user_cols:
        op.drop_column('users', 'token_version')


def downgrade() -> None:
    op.add_column(
        'users',
        sa.Column('token_version', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    )
    op.drop_index(op.f('ix_users_clerk_id'), table_name='users')
    op.drop_column('users', 'clerk_id')
