"""Persist exact grading projection for crash-safe task recovery.

Revision ID: 0017_response_grading_projection
Revises: 0016_learning_lifecycle_v2
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_response_grading_projection"
down_revision: str | None = "0016_learning_lifecycle_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("responses", sa.Column("render_format", sa.String(length=32), nullable=True))
    op.add_column("responses", sa.Column("reveal", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("responses", "reveal")
    op.drop_column("responses", "render_format")
