"""credit period anchor

The account's billing cycle is derived from an anchor instant rather than a stored
rolling timer, so a cycle anchored on the 31st returns to the 31st after a short
month instead of drifting to the 28th permanently. Existing rows are anchored to
the period start they already had, which leaves every current period boundary
unchanged.

No unit conversion is applied. The ledger already stores integer milli-credits
(1 Credit = 1,000 milli-credits), which is the unit this redesign keeps, so
existing balances and debits keep their meaning verbatim and are never
reinterpreted in place.

Revision ID: 0005_credit_period_anchor
Revises: 0004_hierarchy_cache
Create Date: 2026-09-24 10:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0005_credit_period_anchor'
down_revision: str | None = '0004_hierarchy_cache'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('user_credits')]

    if 'period_anchor' not in columns:
        op.add_column(
            'user_credits',
            sa.Column(
                'period_anchor',
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
        # Anchor existing accounts to the period start they are already on, so the
        # next renewal lands where the old rolling timer would have put it.
        op.execute('UPDATE user_credits SET period_anchor = period_start')
        op.alter_column('user_credits', 'period_anchor', nullable=False)
        op.alter_column('user_credits', 'period_anchor', server_default=sa.text('NOW()'))


def downgrade() -> None:
    op.drop_column('user_credits', 'period_anchor')
