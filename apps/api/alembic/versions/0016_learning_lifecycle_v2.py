"""Learning lifecycle v2: two-state sense status + int question ids + level columns.

Redefines the durable learning schema for the level-based prepare/retrieve/evaluate
contract:
  * ``sensestatus`` enum ``{new, learning, review, buried}`` -> ``{new, scheduled}``
    (``acquiring`` is Redis-only, never persisted).
  * ``responses.question_id`` ``str`` -> ``BigInteger`` (lexi question ids are int).
  * ``responses.requested_level`` / ``responses.served_level`` added so an async
    settle can recompute ``is_fallback = served_level < requested_level`` after the
    ephemeral session state has expired.

Forward revision on the live head; the baseline owns all non-learning tables and
is not squashed.  Greenfield (no production learning data), so the enum recreate
and the id conversion are safe.

Revision ID: 0016_learning_lifecycle_v2
Revises: 0015_async_task_deliveries
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_learning_lifecycle_v2"
down_revision: str | None = "0015_async_task_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- sensestatus enum recreate {new,learning,review,buried} -> {new,scheduled}.
    # PG cannot drop enum values in place, so build a fresh type and swap the column.
    op.execute("ALTER TABLE user_sense_stats ALTER COLUMN status DROP DEFAULT")
    op.execute("CREATE TYPE sensestatus_v2 AS ENUM ('new', 'scheduled')")
    # Map any legacy label: review -> scheduled; learning/buried/new -> new.
    op.execute(
        "ALTER TABLE user_sense_stats ALTER COLUMN status TYPE sensestatus_v2 "
        "USING (CASE WHEN status = 'review' THEN 'scheduled' ELSE 'new' END)"
        "::text::sensestatus_v2"
    )
    op.execute("DROP TYPE sensestatus")
    op.execute("ALTER TYPE sensestatus_v2 RENAME TO sensestatus")
    op.execute("ALTER TABLE user_sense_stats ALTER COLUMN status SET DEFAULT 'new'")

    # --- responses.question_id str -> bigint (lexi question ids are int end-to-end).
    op.execute(
        "ALTER TABLE responses ALTER COLUMN question_id TYPE bigint "
        "USING question_id::bigint"
    )

    # --- durable requested/served level so async settle survives Redis expiry.
    op.add_column("responses", sa.Column("requested_level", sa.Integer(), nullable=True))
    op.add_column("responses", sa.Column("served_level", sa.Integer(), nullable=True))


def downgrade() -> None:
    raise RuntimeError(
        "learning lifecycle v2 is forward-only: it recreates the sensestatus enum "
        "and converts question_id; forward-fix or restore from backup, never drop "
        "live schema"
    )
