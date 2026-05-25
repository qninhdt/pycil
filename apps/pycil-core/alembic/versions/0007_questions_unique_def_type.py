"""Add UNIQUE(definition_id, type) on questions; idempotent retries safe.

Revision ID: 0007_questions_unique_def_type
Revises: 0006_subscription_event_ordering
Create Date: 2026-05-26

Wrapped in a single transaction with `LOCK TABLE questions IN ACCESS
EXCLUSIVE MODE` to close the race where in-flight worker generate_question
INSERTs land between dedup and ALTER. Deploy procedure pauses arq workers
before this migration; see docs/deployment-guide.md.
"""
from __future__ import annotations

from alembic import op


revision = "0007_questions_unique_def_type"
down_revision = "0006_subscription_event_ordering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("LOCK TABLE questions IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """
        DELETE FROM questions
         WHERE id IN (
           SELECT id FROM (
             SELECT id,
                    ROW_NUMBER() OVER (
                      PARTITION BY definition_id, type
                      ORDER BY created_at ASC
                    ) AS rn
               FROM questions
           ) t WHERE t.rn > 1
         )
        """
    )
    op.execute(
        "ALTER TABLE questions "
        "ADD CONSTRAINT questions_definition_id_type_unique "
        "UNIQUE (definition_id, type)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE questions "
        "DROP CONSTRAINT IF EXISTS questions_definition_id_type_unique"
    )
