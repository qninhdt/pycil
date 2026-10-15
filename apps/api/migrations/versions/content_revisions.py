"""Durable content patches with commit-ordered publication IDs."""

from alembic import op

revision = "content_revisions"
down_revision = "user_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SEQUENCE content_revision_id_seq AS BIGINT CACHE 1")
    op.execute("""
        CREATE TABLE content_revisions (
            id BIGINT PRIMARY KEY DEFAULT nextval('content_revision_id_seq'),
            entity_type TEXT NOT NULL,
            entity_id BIGINT NOT NULL,
            op JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_content_revisions_entity_type
                CHECK (entity_type IN ('word','question_artifact','theme')),
            CONSTRAINT ck_content_revisions_positive_entity_id CHECK (entity_id > 0),
            CONSTRAINT ck_content_revisions_patch_array
                CHECK (jsonb_typeof(op) = 'array' AND jsonb_array_length(op) > 0)
        )
    """)
    op.execute("ALTER SEQUENCE content_revision_id_seq OWNED BY content_revisions.id")
    op.create_index(
        "ix_content_revisions_entity", "content_revisions", ["entity_type", "entity_id", "id"]
    )


def downgrade():
    raise RuntimeError("Content history must be retained; restore a compatible release instead")
