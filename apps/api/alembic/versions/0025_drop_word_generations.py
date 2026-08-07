"""Drop the superseded word-generation table.

Word generation is tracked by ``async_tasks`` for both producers: the HTTP route
and the assistant tool. This table backed a second, parallel implementation that
carried its own status enum, lease columns and reconciler while charging the same
Redis quota, so a learner's budget was spent against work recorded in two places.

Forward-only, like the migrations that built it: the rows are reproducible
dictionary work, and no reader has consumed them since the durable task resource
took over.

Revision ID: 0025_drop_word_generations
Revises: 0024_assistant_ondelete
"""

from alembic import op

revision = "0025_drop_word_generations"
down_revision = "0024_assistant_ondelete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Indexes go with the table; naming them separately would fail on a database
    # where an earlier revision never created them.
    op.drop_table("word_generations")


def downgrade() -> None:
    raise NotImplementedError("durable jobs are forward-only")
