"""Validate additive learning-grading expansion before rollout.

Revision ID: 0005_learning_grading_validate
Revises: 0004_review_history_index
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_learning_grading_validate"
down_revision: str | None = "0004_review_history_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Expand revisions left legacy graded rows readable. This check constrains
    # only new/updated pending state and requires no destructive backfill.
    pending_without_input = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM responses "
            "WHERE grade_status = 'pending' AND raw_answer IS NULL"
        )
    ).scalar_one()
    if pending_without_input:
        raise RuntimeError(
            "cannot validate grading schema: "
            f"{pending_without_input} legacy pending response(s) have no raw answer; "
            "resolve or explicitly close them before retrying the upgrade"
        )
    op.create_check_constraint(
        "ck_responses_pending_has_raw_answer",
        "responses",
        "grade_status <> 'pending' OR raw_answer IS NOT NULL",
    )
    op.execute(
        sa.text(
            "UPDATE responses SET grading_fence = 0 WHERE grading_fence IS NULL"
        )
    )


def downgrade() -> None:
    raise RuntimeError("0005 is additive; rollback application code or forward-fix, never drop live schema")
