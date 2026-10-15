"""Preserve existing accounts while naming the Clerk identity explicitly."""

from alembic import op

revision = "user_identity"
down_revision = "initial"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "clerk_subject", new_column_name="clerk_id")
    op.execute("ALTER TABLE users RENAME CONSTRAINT uq_users_clerk_subject TO uq_users_clerk_id")


def downgrade():
    op.execute("ALTER TABLE users RENAME CONSTRAINT uq_users_clerk_id TO uq_users_clerk_subject")
    op.alter_column("users", "clerk_id", new_column_name="clerk_subject")
