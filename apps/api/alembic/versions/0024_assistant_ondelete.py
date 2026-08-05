"""Express the assistant deletion order in the database.

Revision ID: 0024_assistant_ondelete
Revises: 0023_task_dispatch_column

Two places hand-ordered the same assistant cascade with string-built SQL:
`account_lifecycle/service.py` and `reconcile_assistant_retention.py`. The plan
said `ondelete=` already covered it — measured on the live database, it did not:
all eight assistant foreign keys were `NO ACTION`, and the only non-`NO ACTION`
rules in the whole schema were `review_log.node_id` and `session_summaries.node_id`,
both `SET NULL`. Removing the hand-ordered deletes without this migration would
have broken `DELETE /me` again.

Three internal edges become CASCADE, so deleting a thread reaches its runs, their
events and their actions without the caller sequencing it:

    assistant_runs.thread_id      -> assistant_threads  CASCADE
    assistant_run_events.run_id   -> assistant_runs     CASCADE
    assistant_actions.run_id      -> assistant_runs     CASCADE

`assistant_action_audit.action_id` becomes SET NULL rather than CASCADE. The audit
row is the policy-required record and has to outlive the action it describes —
retention already does exactly this by hand before deleting actions, and its test
asserts the audit survives with a null `action_id`. CASCADE here would delete the
evidence.

The `owner_id`/`actor_id` edges onto `users` stay `NO ACTION` on purpose. Account
deletion needs to fail loudly if a table is forgotten, which is what caught the
four missing statements in the first place; a silent CASCADE would have hidden them.

Reversible: `downgrade` restores every constraint to `NO ACTION`.
"""

from alembic import op

revision = "0024_assistant_ondelete"
down_revision = "0023_task_dispatch_column"
branch_labels = None
depends_on = None

# (table, constraint, column, referred table, ondelete)
_EDGES = (
    (
        "assistant_runs",
        "assistant_runs_thread_id_fkey",
        "thread_id",
        "assistant_threads",
        "CASCADE",
    ),
    (
        "assistant_run_events",
        "assistant_run_events_run_id_fkey",
        "run_id",
        "assistant_runs",
        "CASCADE",
    ),
    ("assistant_actions", "assistant_actions_run_id_fkey", "run_id", "assistant_runs", "CASCADE"),
    (
        "assistant_action_audit",
        "assistant_action_audit_action_id_fkey",
        "action_id",
        "assistant_actions",
        "SET NULL",
    ),
)


def upgrade() -> None:
    for table, constraint, column, referred, rule in _EDGES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, referred, [column], ["id"], ondelete=rule)


def downgrade() -> None:
    for table, constraint, column, referred, _rule in _EDGES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, referred, [column], ["id"])
