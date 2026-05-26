"""Add last_llm_response_at timestamp + last_llm_response on questions.

Revision ID: 0008_llm_response_retry_cache
Revises: 0007_questions_unique_def_type
Create Date: 2026-05-26

Cache the LLM response on the job row so a retry that fires after a
successful LLM call but a failed DB write reuses the response instead
of re-paying the model. Also adds the same column on `questions` job
side via the user_question_jobs table (reuses existing user_term_jobs
mechanism for question generation flows).
"""
from __future__ import annotations

from alembic import op


revision = "0008_llm_response_retry_cache"
down_revision = "0007_questions_unique_def_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE user_term_jobs
        ADD COLUMN IF NOT EXISTS last_llm_response_at TIMESTAMPTZ
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE user_term_jobs DROP COLUMN IF EXISTS last_llm_response_at"
    )
