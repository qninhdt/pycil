"""Give the dispatch payload its own column, separate from the outcome.

Revision ID: 0023_task_dispatch_column
Revises: 0022_bound_interest_lifetime

`async_tasks.result` carried two schemas: `submit_or_join` wrote
`{"dispatch": ...}` for re-enqueue, and `transition_task` later assigned
`task.result = result` — a parameter that defaults to None. So a requeue
transition erased the dispatch payload, the task then failed
`list_reenqueueable_tasks`'s `dispatch` filter, and every subsequent sweep skipped
it. The row stayed queued forever with nothing reporting it, which is the same
silent-unrecoverable shape as the unhandled-kind branch.

Reproduced before the change: after one QUEUED transition, `result` was None and
the reconciler returned 0 rows for a task that had just asked to be retried.

Measured on the live database before migrating: 0 of 103 tasks still had
`result->'dispatch'` — every one had already been overwritten by its terminal
transition — and 0 tasks were queued or running, so there was nothing in flight to
lose. The copy below is therefore a no-op here, and is written anyway because it is
not a no-op on a database migrated mid-flight.

Reversible: `downgrade` folds the column back under `result` for rows that still
have a dispatch and no outcome, then drops it. A row that has since settled keeps
its outcome, because that is the value `result` is supposed to hold.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0023_task_dispatch_column"
down_revision = "0022_bound_interest_lifetime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "async_tasks",
        sa.Column("dispatch", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Move any surviving dispatch payload across, and stop `result` describing it.
    op.execute(
        """
        UPDATE async_tasks
           SET dispatch = result -> 'dispatch',
               result = NULL
         WHERE result ? 'dispatch'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE async_tasks
           SET result = jsonb_build_object('dispatch', dispatch)
         WHERE dispatch IS NOT NULL
           AND result IS NULL
        """
    )
    op.drop_column("async_tasks", "dispatch")
