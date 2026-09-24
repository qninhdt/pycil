"""Store assistant usage and tariff details with its cumulative debit.

Revision ID: 0008_credit_debit_usage_snapshot
Revises: 0007_drop_assistant_runs
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_credit_debit_usage_snapshot"
down_revision: str | None = "0007_drop_assistant_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "credit_debits",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credit_debits", "details")
