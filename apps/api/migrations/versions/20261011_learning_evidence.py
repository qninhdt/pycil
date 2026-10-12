"""Replace rating-based selection with diagnostic evidence and per-Sense Elo."""

import sqlalchemy as sa
from alembic import op

revision = "20261011_learning"
down_revision = "20261009_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_senses", sa.Column("elo", sa.Float(), nullable=False, server_default="600"))
    op.alter_column("user_senses", "elo", server_default=None)
    op.alter_column("user_senses", "last_review_at", new_column_name="last_exposure_at")
    op.drop_constraint(op.f("ck_user_senses_rating"), "user_senses", type_="check")
    op.drop_column("user_senses", "last_rating")
    op.execute("""UPDATE users SET settings = jsonb_set(settings, '{learning}',
        ((settings->'learning') - 'show_explanations') || jsonb_build_object(
            'questions_per_sense',
                LEAST(3, COALESCE((settings->'learning'->>'questions_per_sense')::int, 2)),
            'max_sense_count',
                LEAST(20, COALESCE((settings->'learning'->>'max_sense_count')::int, 10))))
        WHERE settings ? 'learning'""")


def downgrade():
    raise RuntimeError("Diagnostic learning replaces the old rating contract")
