"""Fresh Pycil baseline: UUID identities, unordered membership and query indexes.

Revision ID: 0001_baseline
Revises: None
Frozen from the new models, not from archived Pycil implementation.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names(schema="public"))
    if existing - {"alembic_version"}:
        raise RuntimeError(
            "Fresh Pycil baseline requires an empty public schema; no implicit reset"
        )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clerk_subject", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "plan",
            sa.Enum("FREE", "PRO", name="plan", native_enum=False, create_constraint=True),
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
            "jsonb_typeof(settings) = 'object'", name=op.f("ck_users_settings_object")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("clerk_subject", name=op.f("uq_users_clerk_subject")),
    )
    op.create_table(
        "word_generations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("available_id", sa.String(length=255), nullable=False),
        sa.Column("target", sa.String(length=512), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED",
                "RUNNING",
                "SUCCEEDED",
                "FAILED",
                name="generationstatus",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_word_generations_nonnegative_attempts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_word_generations")),
        sa.UniqueConstraint(
            "available_id", "target", name=op.f("uq_word_generations_available_id")
        ),
    )
    op.create_index(
        "ix_generation_queue",
        "word_generations",
        ["status", "next_attempt_at", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "collection_nodes",
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
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "visibility",
            sa.Enum(
                "PRIVATE", "PUBLIC", name="visibility", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(type = 'REFERENCE') = (reference_id IS NOT NULL)",
            name=op.f("ck_collection_nodes_reference_shape"),
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id != id", name=op.f("ck_collection_nodes_not_own_parent")
        ),
        sa.CheckConstraint(
            "reference_id IS NULL OR reference_id != id",
            name=op.f("ck_collection_nodes_not_own_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_collection_nodes_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["collection_nodes.id"],
            name=op.f("fk_collection_nodes_parent_id_collection_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["collection_nodes.id"],
            name=op.f("fk_collection_nodes_reference_id_collection_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_nodes")),
    )
    op.create_index(
        op.f("ix_collection_nodes_reference_id"), "collection_nodes", ["reference_id"], unique=False
    )
    op.create_index("ix_collection_nodes_parent_id", "collection_nodes", ["parent_id"])
    op.create_index(
        "ix_nodes_public_root_order",
        "collection_nodes",
        ["created_at", "id"],
        postgresql_where=sa.text(
            "parent_id IS NULL AND deleted_at IS NULL AND visibility = 'PUBLIC'"
        ),
    )
    op.create_index(
        "ix_nodes_owner_parent_order",
        "collection_nodes",
        ["owner_id", "parent_id", "created_at", "id"],
        unique=False,
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
    op.create_index("ix_conversations_retention", "conversations", ["updated_at", "id"])
    op.create_table(
        "review_log",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.Uuid(), nullable=False),
        sa.Column("sense_id", sa.Integer(), nullable=False),
        sa.Column(
            "rating",
            sa.Enum(
                "AGAIN",
                "HARD",
                "GOOD",
                "EASY",
                name="rating",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("mastery_after", sa.Integer(), nullable=False),
        sa.Column("due_after", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mastery_after BETWEEN 0 AND 100", name=op.f("ck_review_log_mastery_range")
        ),
        sa.ForeignKeyConstraint(
            ["sense_id"],
            ["lexi.senses.id"],
            name=op.f("fk_review_log_sense_id_senses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_review_log_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "event_key", name=op.f("pk_review_log")),
    )
    op.create_index(
        "ix_reviews_user_time", "review_log", ["user_id", "accepted_at", "event_key"], unique=False
    )
    op.create_index("ix_review_log_sense_id", "review_log", ["sense_id"])
    op.create_table(
        "sense_memory",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("sense_id", sa.Integer(), nullable=False),
        sa.Column("stability", sa.Float(), nullable=False),
        sa.Column("difficulty", sa.Float(), nullable=False),
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
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("lapse_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_count > 0 AND lapse_count >= 0", name=op.f("ck_sense_memory_valid_counts")
        ),
        sa.CheckConstraint(
            "stability > 0 AND difficulty > 0", name=op.f("ck_sense_memory_positive_memory")
        ),
        sa.ForeignKeyConstraint(
            ["sense_id"],
            ["lexi.senses.id"],
            name=op.f("fk_sense_memory_sense_id_senses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sense_memory_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "sense_id", name=op.f("pk_sense_memory")),
    )
    op.create_index(
        "ix_memory_user_due", "sense_memory", ["user_id", "due_at", "sense_id"], unique=False
    )
    op.create_index("ix_sense_memory_sense_id", "sense_memory", ["sense_id"])
    op.create_index(
        "ix_memory_user_stability", "sense_memory", ["user_id", "stability", "sense_id"]
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
        "deck_senses",
        sa.Column("deck_id", sa.Uuid(), nullable=False),
        sa.Column("sense_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["deck_id"],
            ["collection_nodes.id"],
            name=op.f("fk_deck_senses_deck_id_collection_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sense_id"],
            ["lexi.senses.id"],
            name=op.f("fk_deck_senses_sense_id_senses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("deck_id", "sense_id", name=op.f("pk_deck_senses")),
    )
    op.create_index("ix_deck_senses_sense_id", "deck_senses", ["sense_id"])
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
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("units", sa.BigInteger(), nullable=False),
        sa.Column("unmetered_calls", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
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
    for table in (
        "usage_events",
        "deck_senses",
        "usage_periods",
        "sense_memory",
        "review_log",
        "conversations",
        "collection_nodes",
        "word_generations",
        "users",
    ):
        op.drop_table(table)
