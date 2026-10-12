"""Fresh Pycil schema; historical upgrades are intentionally unsupported."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261009_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names(schema="public"))
    if existing - {"alembic_version"}:
        raise RuntimeError("Baseline requires an empty public schema; existing data is protected")
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clerk_subject", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("handle", sa.String(length=30), nullable=True),
        sa.Column("bio", sa.String(length=500), nullable=True),
        sa.Column(
            "plan",
            sa.Enum("FREE", "PRO", name="plan", native_enum=False, create_constraint=False),
            nullable=False,
        ),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cycle_anchor", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "handle IS NULL OR handle ~ '^[a-z][a-z0-9_]{2,29}$'",
            name=op.f("ck_users_handle_shape"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(settings) = 'object'", name=op.f("ck_users_settings_object")
        ),
        sa.CheckConstraint("plan IN ('FREE', 'PRO')", name=op.f("ck_users_plan")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("clerk_subject", name=op.f("uq_users_clerk_subject")),
        sa.UniqueConstraint("handle", name=op.f("uq_users_handle")),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        "ix_conversations_owner_updated",
        "conversations",
        ["user_id", "updated_at", "id"],
        unique=False,
    )
    op.create_table(
        "nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "FOLDER",
                "DECK",
                "REFERENCE",
                name="nodetype",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple'::regconfig, coalesce(name, '')), 'A') || "
                "setweight(to_tsvector('simple'::regconfig, coalesce(description, '')), 'B')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum(
                "NORMAL",
                "LIBRARY_ROOT",
                "PERSONAL_ROOT",
                "PUBLISHED_ROOT",
                name="noderole",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "space",
            sa.Enum(
                "LIBRARY",
                "PERSONAL",
                "PUBLISHED",
                name="nodespace",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(role = 'LIBRARY_ROOT') = (parent_id IS NULL)", name=op.f("ck_nodes_root_shape")
        ),
        sa.CheckConstraint(
            "(type = 'REFERENCE') = (reference_id IS NOT NULL)",
            name=op.f("ck_nodes_reference_shape"),
        ),
        sa.CheckConstraint(
            "role = 'NORMAL' OR type = 'FOLDER'", name=op.f("ck_nodes_system_folder")
        ),
        sa.CheckConstraint(
            "role IN ('NORMAL', 'LIBRARY_ROOT', 'PERSONAL_ROOT', 'PUBLISHED_ROOT')",
            name=op.f("ck_nodes_noderole"),
        ),
        sa.CheckConstraint(
            "space IN ('LIBRARY', 'PERSONAL', 'PUBLISHED')", name=op.f("ck_nodes_nodespace")
        ),
        sa.CheckConstraint(
            "type IN ('FOLDER', 'DECK', 'REFERENCE')", name=op.f("ck_nodes_nodetype")
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id != id", name=op.f("ck_nodes_not_own_parent")
        ),
        sa.CheckConstraint(
            "reference_id IS NULL OR reference_id != id", name=op.f("ck_nodes_not_own_reference")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "parent_id"],
            ["nodes.owner_id", "nodes.id"],
            name=op.f("fk_nodes_owner_id_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_nodes_owner_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["nodes.id"],
            name=op.f("fk_nodes_reference_id_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nodes")),
        sa.UniqueConstraint("owner_id", "id", name=op.f("uq_nodes_owner_id")),
    )
    op.create_index(
        "ix_nodes_owner_parent_order",
        "nodes",
        ["owner_id", "parent_id", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(op.f("ix_nodes_parent_id"), "nodes", ["parent_id"], unique=False)
    op.create_index(
        "ix_nodes_published_order",
        "nodes",
        ["created_at", "id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND space = 'PUBLISHED' AND role = 'NORMAL'"),
    )
    op.create_index(
        "ix_nodes_published_owner_order",
        "nodes",
        ["owner_id", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND space = 'PUBLISHED' AND role = 'NORMAL'"),
    )
    op.create_index(op.f("ix_nodes_reference_id"), "nodes", ["reference_id"], unique=False)
    op.create_index(
        "ix_nodes_search_vector", "nodes", ["search_vector"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "uq_nodes_owner_role",
        "nodes",
        ["owner_id", "role"],
        unique=True,
        postgresql_where=sa.text("role != 'NORMAL'"),
    )
    op.create_table(
        "review_log",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_day", sa.Date(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_review_log_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "event_key", name=op.f("pk_review_log")),
    )
    op.create_table(
        "usage_periods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("allowance_units", sa.BigInteger(), nullable=False),
        sa.Column("used_units", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "allowance_units >= 0 AND used_units >= 0",
            name=op.f("ck_usage_periods_nonnegative_units"),
        ),
        sa.CheckConstraint("period_end > period_start", name=op.f("ck_usage_periods_valid_period")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_usage_periods_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_periods")),
        sa.UniqueConstraint("user_id", "period_start", name=op.f("uq_usage_periods_user_id")),
    )
    op.create_table(
        "user_daily_activity",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("applied_events", sa.Integer(), nullable=False),
        sa.Column("practice_events", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "applied_events >= 0 AND practice_events >= 0",
            name=op.f("ck_user_daily_activity_nonnegative_events"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_daily_activity_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "day", name=op.f("pk_user_daily_activity")),
    )
    op.create_table(
        "user_senses",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("sense_id", sa.Integer(), nullable=False),
        sa.Column("stability", sa.Double(), nullable=False),
        sa.Column("difficulty", sa.Double(), nullable=False),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_rating",
            sa.Enum(
                "AGAIN",
                "HARD",
                "GOOD",
                "EASY",
                name="rating",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("lapse_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "last_rating IN ('AGAIN', 'HARD', 'GOOD', 'EASY')", name=op.f("ck_user_senses_rating")
        ),
        sa.CheckConstraint(
            "review_count > 0 AND lapse_count >= 0", name=op.f("ck_user_senses_valid_counts")
        ),
        sa.CheckConstraint(
            "stability > 0 AND difficulty > 0", name=op.f("ck_user_senses_positive_memory")
        ),
        sa.ForeignKeyConstraint(
            ["sense_id"],
            ["lexi.senses.id"],
            name=op.f("fk_user_senses_sense_id_senses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_senses_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "sense_id", name=op.f("pk_user_senses")),
    )
    op.create_index(op.f("ix_user_senses_sense_id"), "user_senses", ["sense_id"], unique=False)
    op.create_index(
        "ix_user_senses_user_due", "user_senses", ["user_id", "due_at", "sense_id"], unique=False
    )
    op.create_table(
        "deck_senses",
        sa.Column("deck_id", sa.Uuid(), nullable=False),
        sa.Column("sense_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["deck_id"], ["nodes.id"], name=op.f("fk_deck_senses_deck_id_nodes"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["sense_id"],
            ["lexi.senses.id"],
            name=op.f("fk_deck_senses_sense_id_senses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("deck_id", "sense_id", name=op.f("pk_deck_senses")),
    )
    op.create_index(op.f("ix_deck_senses_sense_id"), "deck_senses", ["sense_id"], unique=False)
    op.create_table(
        "node_paths",
        sa.Column("ancestor_id", sa.Uuid(), nullable=False),
        sa.Column("descendant_id", sa.Uuid(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(ancestor_id = descendant_id) = (depth = 0)", name=op.f("ck_node_paths_self_depth")
        ),
        sa.CheckConstraint("depth >= 0", name=op.f("ck_node_paths_nonnegative_depth")),
        sa.ForeignKeyConstraint(
            ["ancestor_id"],
            ["nodes.id"],
            name=op.f("fk_node_paths_ancestor_id_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["descendant_id"],
            ["nodes.id"],
            name=op.f("fk_node_paths_descendant_id_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ancestor_id", "descendant_id", name=op.f("pk_node_paths")),
    )
    op.create_index(
        "ix_node_paths_descendant", "node_paths", ["descendant_id", "ancestor_id"], unique=False
    )
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("execution_key", sa.Uuid(), nullable=False),
        sa.Column(
            "feature",
            sa.Enum(
                "ASSISTANT",
                "ADVANCED_GRADING",
                name="feature",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("units", sa.BigInteger(), nullable=False),
        sa.Column("unmetered_calls", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "feature IN ('ASSISTANT', 'ADVANCED_GRADING')", name=op.f("ck_usage_events_feature")
        ),
        sa.CheckConstraint("units >= 0", name=op.f("ck_usage_events_nonnegative_units")),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["usage_periods.id"],
            name=op.f("fk_usage_events_period_id_usage_periods"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_events")),
        sa.UniqueConstraint("execution_key", name=op.f("uq_usage_events_execution_key")),
    )
    op.create_index(op.f("ix_usage_events_period_id"), "usage_events", ["period_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_usage_events_period_id"), table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("ix_node_paths_descendant", table_name="node_paths")
    op.drop_table("node_paths")
    op.drop_index(op.f("ix_deck_senses_sense_id"), table_name="deck_senses")
    op.drop_table("deck_senses")
    op.drop_index("ix_user_senses_user_due", table_name="user_senses")
    op.drop_index(op.f("ix_user_senses_sense_id"), table_name="user_senses")
    op.drop_table("user_senses")
    op.drop_table("user_daily_activity")
    op.drop_table("usage_periods")
    op.drop_table("review_log")
    op.drop_index(
        "uq_nodes_owner_role", table_name="nodes", postgresql_where=sa.text("role != 'NORMAL'")
    )
    op.drop_index("ix_nodes_search_vector", table_name="nodes", postgresql_using="gin")
    op.drop_index(op.f("ix_nodes_reference_id"), table_name="nodes")
    op.drop_index(
        "ix_nodes_published_owner_order",
        table_name="nodes",
        postgresql_where=sa.text("deleted_at IS NULL AND space = 'PUBLISHED' AND role = 'NORMAL'"),
    )
    op.drop_index(
        "ix_nodes_published_order",
        table_name="nodes",
        postgresql_where=sa.text("deleted_at IS NULL AND space = 'PUBLISHED' AND role = 'NORMAL'"),
    )
    op.drop_index(op.f("ix_nodes_parent_id"), table_name="nodes")
    op.drop_index(
        "ix_nodes_owner_parent_order",
        table_name="nodes",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("nodes")
    op.drop_index("ix_conversations_owner_updated", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("users")
