"""Add a terminal expired grade state for raw-answer retention.

Revision ID: 0006_grading_expiry
Revises: 0005_learning_grading_validate
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_grading_expiry"
down_revision: str | None = "0005_learning_grading_validate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Kept separate from the validation revision: PostgreSQL makes a newly
    # added enum value visible for application writes after this migration ends.
    op.execute("ALTER TYPE gradestatus ADD VALUE IF NOT EXISTS 'expired'")


def downgrade() -> None:
    raise RuntimeError(
        "0006 is additive; rollback application code or forward-fix, never drop live schema"
    )
