"""Optional identity metadata; existing users remain unnamed, not auto-assigned."""

import sqlalchemy as sa
from alembic import op

revision = "0005_profile_handle_bio"
down_revision = "0004_node_search"
branch_labels = depends_on = None


def upgrade():
    op.add_column("users", sa.Column("handle", sa.String(30), nullable=True))
    op.add_column("users", sa.Column("bio", sa.String(500), nullable=True))
    op.create_unique_constraint("uq_users_handle", "users", ["handle"])
    op.create_check_constraint(
        "handle_shape", "users", "handle IS NULL OR handle ~ '^[a-z][a-z0-9_]{2,29}$'"
    )


def downgrade():
    op.drop_constraint(op.f("ck_users_handle_shape"), "users")
    op.drop_constraint("uq_users_handle", "users")
    op.drop_column("users", "bio")
    op.drop_column("users", "handle")
