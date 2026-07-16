"""Add the access path used by bounded folder-history reads.

Revision ID: 0004_review_history_index
Revises: 0003_learning_grading_expand
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_review_history_index"
down_revision: str | None = "0003_learning_grading_expand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_review_log_user_sense_time",
        "review_log",
        ["user_id", "sense_id", "reviewed_at"],
    )


def downgrade() -> None:
    raise RuntimeError("0004 is additive; rollback application code or forward-fix, never drop live schema")
