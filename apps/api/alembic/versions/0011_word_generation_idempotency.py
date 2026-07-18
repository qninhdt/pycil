"""Make browser word-generation submissions idempotent.

Revision ID: 0011_word_generation_idempotency
Revises: 0010_durable_word_generations
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_word_generation_idempotency"
down_revision = "0010_durable_word_generations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_word_generations_owner_idempotency_key",
        "word_generations",
        ["owner_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    raise NotImplementedError("durable jobs are forward-only")
