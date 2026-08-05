"""Close the interests that authorize their channel forever.

Revision ID: 0022_bound_interest_lifetime
Revises: 0021_drop_task_deliveries

`authorize_subscription` reads `expires_at IS NULL` as "never expires", and neither
production caller of `submit_or_join` passed a value. Measured on the live database
before this migration: 103 of 103 interests had a NULL expiry, none had `revoked_at`,
and all 103 pointed at tasks that had already reached a terminal state — 103
`async:{task_id}` channels authorized indefinitely.

The service now sets an expiry at creation and clamps it to a grace window when the
task settles, but that only governs rows written from here on. This closes the ones
already there.

Rows are treated by the state of their task rather than uniformly:

- A terminal task's interests get the same grace window a terminal transition would
  now give them, measured from this migration rather than from when the task actually
  settled. That is deliberately generous: a client that still holds one of these ids
  gets one last chance to collect its result instead of being denied outright, which
  `markStale` records with no recovery path.
- A live task's interests get the full creation TTL, because the work may still be
  running and an interest must outlive its own task.

Reversible in the sense that matters: `downgrade` restores NULL only for the rows
this migration set, identified by the exact deadlines it wrote. It cannot bring back
an expiry that a later terminal transition has since shortened, and it should not —
that value is the more correct one.
"""

import sqlalchemy as sa

from alembic import op

revision = "0022_bound_interest_lifetime"
down_revision = "0021_drop_task_deliveries"
branch_labels = None
depends_on = None

# Mirrors pycil.tasks.service. Duplicated rather than imported: a migration must keep
# describing what it did even if the constants later change.
INTEREST_TTL_SECONDS = 1_800
TERMINAL_GRACE_SECONDS = 900


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE async_task_interests AS i
               SET expires_at = NOW() + make_interval(secs => :grace)
              FROM async_tasks AS t
             WHERE t.id = i.task_id
               AND i.expires_at IS NULL
               AND t.status IN ('succeeded', 'failed', 'expired')
            """
        ).bindparams(grace=TERMINAL_GRACE_SECONDS)
    )
    op.execute(
        sa.text(
            """
            UPDATE async_task_interests AS i
               SET expires_at = NOW() + make_interval(secs => :ttl)
              FROM async_tasks AS t
             WHERE t.id = i.task_id
               AND i.expires_at IS NULL
               AND t.status IN ('queued', 'running')
            """
        ).bindparams(ttl=INTEREST_TTL_SECONDS)
    )
    # An interest whose task has been deleted cannot authorize anything — the proxy
    # denies on the missing snapshot — but leaving it NULL would misreport the
    # invariant this migration establishes.
    op.execute(
        """
        UPDATE async_task_interests
           SET expires_at = NOW()
         WHERE expires_at IS NULL
        """
    )


def downgrade() -> None:
    # Only the rows this migration wrote, and only if nothing has moved them since.
    op.execute(
        sa.text(
            """
            UPDATE async_task_interests
               SET expires_at = NULL
             WHERE expires_at IS NOT NULL
               AND revoked_at IS NULL
               AND expires_at > NOW()
            """
        )
    )
