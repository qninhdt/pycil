"""Let a deleted deck release the review history that points at it.

``review_log.node_id`` and ``session_summaries.node_id`` both referenced
``nodes.id`` with no ``ON DELETE`` action, so the constraint defaulted to
NO ACTION: any hard delete of a node was blocked while a review row still named
it.

That was latent until ``review_log.node_id`` started being populated. Two real
paths reach it:

* ``account_lifecycle`` hard-deletes nodes. It deletes ``review_log WHERE
  user_id = :user_id`` first, which covers the owner's own history — but not
  another learner's. Study someone's public deck, then let that person delete
  their account, and ``DELETE FROM nodes WHERE author_id`` fails on a foreign key
  from a row belonging to a third party the statement never looks at.
* A grade landing for a node that has just been hard-deleted would raise
  ``ForeignKeyViolationError`` mid-transaction and lose a verdict the learner has
  already paid an LLM call for.

SET NULL rather than CASCADE, deliberately. The FSRS history is the learner's,
not the deck's: mastery and stability stay valid after a deck is gone, and the
review must not disappear with it. Dropping to NULL simply returns these rows to
the state every row was in before ``node_id`` was written — a state both readers
already handle, since the dashboard filters on
``ReviewLog.node_id.is_not(None)``.

Revision ID: 0020_review_history_ondelete
Revises: 0019_user_learning_settings
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_review_history_ondelete"
down_revision: str | None = "0019_user_learning_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, constraint, column) for every FK from review history to `nodes`.
_TARGETS = (
    ("review_log", "review_log_node_id_fkey", "node_id"),
    ("session_summaries", "session_summaries_node_id_fkey", "node_id"),
)


def upgrade() -> None:
    for table, constraint, column in _TARGETS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            "nodes",
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table, constraint, column in _TARGETS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, "nodes", [column], ["id"])
