"""Persist FSRS snapshots on each terminal response for poll/push parity.

Revision ID: 0007_response_mastery
Revises: 0006_grading_expiry
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_response_mastery"
down_revision: str | None = "0006_grading_expiry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("responses", sa.Column("mastery_before", sa.Integer(), nullable=True))
    op.add_column("responses", sa.Column("mastery_after", sa.Integer(), nullable=True))


def downgrade() -> None:
    raise RuntimeError(
        "0007 is additive; rollback application code or forward-fix, never drop live schema"
    )
