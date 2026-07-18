"""Remove deprecated admin and social product schema.

Revision ID: 0009
Revises: 0008_assistant_agent
"""

from alembic import op

revision = "0009"
down_revision = "0008_assistant_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("user_nodes")
    op.drop_table("folder_attributes")
    op.drop_column("nodes", "fork_count")
    op.drop_column("nodes", "like_count")
    op.drop_column("nodes", "sense_count")
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "banned_at")
    op.drop_column("users", "role")
    op.execute("DROP TYPE IF EXISTS userrole")


def downgrade() -> None:
    raise NotImplementedError("prototype canonicalization is intentionally forward-only")
