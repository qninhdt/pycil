"""Normalize existing names and enforce editable display-name shape."""

from alembic import op

revision = "20261012_profile"
down_revision = "20261011_learning"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE users SET display_name = NULLIF(btrim(display_name), '')")
    op.create_check_constraint(
        op.f("ck_users_display_name_shape"),
        "users",
        "display_name IS NULL OR (display_name = btrim(display_name) "
        "AND length(display_name) BETWEEN 1 AND 255)",
    )


def downgrade():
    op.drop_constraint(op.f("ck_users_display_name_shape"), "users", type_="check")
