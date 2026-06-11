"""Drop the stale UNIQUE(definition_id, type) on questions.

Revision ID: 0024_drop_questions_unique_def_type
Revises: 0023_responses_async_grading

The shared question bank holds multiple variants per
(definition_id, type, difficulty) slot — ``question_bank_target_depth``
defaults to 2 and the read path rotates across variants. The leftover
single-row UNIQUE(definition_id, type) constraint (added before the bank
redesign) forbids the second variant: ``generate_question`` raises
IntegrityError the moment a slot tries to hold more than one row.

Over-generation is bounded by the depth-aware skip in ``generate_question``
plus the per-(definition,type) generation lock, not by this DB constraint —
so dropping it restores the intended bank semantics without unbounding spend.

The plain ``(definition_id, type)`` btree index added in 0022
(``questions_definition_type``) remains and serves the bank read; only the
UNIQUE constraint is removed here.
"""
from __future__ import annotations

from alembic import op

revision = "0024_drop_questions_unique_def_type"
down_revision = "0023_responses_async_grading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE questions "
        "DROP CONSTRAINT IF EXISTS questions_definition_id_type_unique"
    )


def downgrade() -> None:
    # Re-adding the constraint requires the table to currently hold at most one
    # row per (definition_id, type); dedup first, mirroring migration 0007.
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
