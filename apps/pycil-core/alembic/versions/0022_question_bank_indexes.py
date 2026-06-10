"""Question bank: difficulty backfill + read-path indexes.

Revision ID: 0022_question_bank_indexes
Revises: 0021_content_reports

Supports the shared question bank (phase: question-bank-prewarm):

- Backfill ``questions.data->>'difficulty' = 'easy'`` on rows generated before
  difficulty became a bank dimension, so existing (already-paid) questions are
  not orphaned by the difficulty filter and regenerated.
- ``(definition_id, type)`` composite index for the bank read.
- ``responses(question_id, user_id)`` index for the least-seen variant-rotation
  subquery on the per-turn hot path.

Dedup note: there is intentionally NO unique index over
``(definition_id, type, difficulty)`` — the bank holds multiple variants per
slot (TARGET_DEPTH > 1), so such an index would forbid the variants it exists
to store. ``variant_seed`` has no producer, so a UNIQUE over it would be a
no-op (NULLs are distinct in Postgres). Over-generation is bounded by the
depth-aware skip in ``generate_question`` plus the per-(definition,type)
generation lock, not by a DB constraint.
Deploy ordering: the pipeline is migration-then-swap (this backfill runs to
completion against the new image BEFORE traffic is routed to bank-reading code),
so the transient "NULL-difficulty row served but not counted toward depth"
window does not occur in production.

Scale note: ``CREATE INDEX`` (non-concurrent) takes a SHARE lock that blocks
writes on ``questions``/``responses`` for the build duration, and the
``jsonb_set`` backfill is a single full UPDATE. Fine at current table sizes;
switch to ``CREATE INDEX CONCURRENTLY`` (non-transactional migration) + a
batched backfill if these tables grow large enough for the lock window to bite.
"""
from __future__ import annotations

from alembic import op


revision = "0022_question_bank_indexes"
down_revision = "0021_content_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill difficulty on legacy rows that predate the bank dimension.
    op.execute(
        """
        UPDATE questions
           SET data = jsonb_set(data, '{difficulty}', '"easy"', true)
         WHERE data->>'difficulty' IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS questions_definition_type "
        "ON questions(definition_id, type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS responses_question_user "
        "ON responses(question_id, user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS responses_question_user")
    op.execute("DROP INDEX IF EXISTS questions_definition_type")
    # Backfill is not reversed: dropping a difficulty key that some rows always
    # had is ambiguous and unnecessary for rollback safety.
