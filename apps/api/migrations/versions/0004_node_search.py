"""Transactionally maintained weighted node documents; no external search service."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision = "0004_node_search"
down_revision = "0003_learning_batches_activity"
branch_labels = depends_on = None


def upgrade():
    op.add_column(
        "nodes",
        sa.Column(
            "search_vector",
            TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple'::regconfig, coalesce(name, '')), 'A') || "
                "setweight(to_tsvector('simple'::regconfig, coalesce(description, '')), 'B')",
                persisted=True,
            ),
            nullable=False,
        ),
    )
    op.create_index("ix_nodes_search_vector", "nodes", ["search_vector"], postgresql_using="gin")
    op.create_index(
        "ix_nodes_published_owner_order",
        "nodes",
        ["owner_id", "created_at", "id"],
        postgresql_where=sa.text("deleted_at IS NULL AND space = 'PUBLISHED' AND role = 'NORMAL'"),
    )


def downgrade():
    op.drop_index("ix_nodes_published_owner_order", table_name="nodes")
    op.drop_index("ix_nodes_search_vector", table_name="nodes")
    op.drop_column("nodes", "search_vector")
