"""Preserve scheduler state and convert scalar events into immutable batch receipts."""

import hashlib
import json
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003_learning_batches_activity"
down_revision = "0002_nodes_spaces_paths"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    # Validate/transform before DDL. Defaults are frozen from the preceding release.
    for user in connection.execute(sa.text("SELECT id, settings FROM users")).mappings():
        settings = dict(user["settings"])
        ZoneInfo(settings.get("timezone", "UTC"))
        learning = dict(settings.get("learning", {}))
        q, k = learning.pop("question_budget", 30), learning.get("questions_per_sense", 3)
        if type(q) is not int or type(k) is not int or not 1 <= k <= 7 or not k <= q <= 100:
            raise RuntimeError("Invalid legacy learning preferences; resolve before upgrade")
        learning["max_sense_count"] = q // k
        settings["learning"] = learning
        connection.execute(
            sa.text("UPDATE users SET settings=CAST(:settings AS jsonb) WHERE id=:id"),
            {"id": user["id"], "settings": json.dumps(settings)},
        )
    op.rename_table("sense_memory", "user_senses")
    op.drop_index("ix_memory_user_stability", table_name="user_senses")
    op.execute("ALTER INDEX ix_memory_user_due RENAME TO ix_user_senses_user_due")
    op.execute("ALTER INDEX ix_sense_memory_sense_id RENAME TO ix_user_senses_sense_id")
    for old, new in (
        ("pk_sense_memory", "pk_user_senses"),
        ("ck_sense_memory_positive_memory", "ck_user_senses_positive_memory"),
        ("ck_sense_memory_valid_counts", "ck_user_senses_valid_counts"),
        ("ck_sense_memory_rating", "ck_user_senses_rating"),
        ("fk_sense_memory_user_id_users", "fk_user_senses_user_id_users"),
        ("fk_sense_memory_sense_id_senses", "fk_user_senses_sense_id_senses"),
    ):
        op.execute(f"ALTER TABLE user_senses RENAME CONSTRAINT {old} TO {new}")
    op.add_column("review_log", sa.Column("request_hash", sa.Text(), nullable=True))
    op.add_column("review_log", sa.Column("activity_day", sa.Date(), nullable=True))
    op.add_column("review_log", sa.Column("result", JSONB(), nullable=True))
    op.create_table(
        "user_daily_activity",
        sa.Column(
            "user_id", UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("applied_events", sa.Integer(), nullable=False),
        sa.Column("practice_events", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "applied_events >= 0 AND practice_events >= 0", name="nonnegative_events"
        ),
    )
    events = connection.execute(
        sa.text("""
        SELECT r.*, timezone(COALESCE(u.settings->>'timezone','UTC'), r.accepted_at)::date AS day
        FROM review_log r JOIN users u ON u.id=r.user_id
    """)
    )
    for event in events.mappings():
        body = {"results": [{"sense_id": event["sense_id"], "rating": event["rating"]}]}
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
        item = {
            **body["results"][0],
            "applied": event["applied"],
            "accepted_at": event["accepted_at"].isoformat().replace("+00:00", "Z"),
            "due_after": event["due_after"].isoformat().replace("+00:00", "Z"),
        }
        result = {
            "accepted_at": item["accepted_at"],
            "activity_day": event["day"].isoformat(),
            "results": [item],
        }
        connection.execute(
            sa.text("""UPDATE review_log SET request_hash=:hash, activity_day=:day,
            result=CAST(:result AS jsonb) WHERE user_id=:user AND event_key=:key"""),
            {
                "hash": digest,
                "day": event["day"],
                "result": json.dumps(result),
                "user": event["user_id"],
                "key": event["event_key"],
            },
        )
    op.execute("""INSERT INTO user_daily_activity SELECT user_id, activity_day,
        count(*) FILTER (WHERE applied), count(*) FILTER (WHERE NOT applied)
        FROM review_log GROUP BY user_id, activity_day""")
    op.drop_index("ix_reviews_user_time", table_name="review_log")
    op.drop_index("ix_review_log_sense_id", table_name="review_log")
    for name in (
        "ck_review_log_mastery_range",
        "ck_review_log_rating",
        "fk_review_log_sense_id_senses",
    ):
        op.drop_constraint(op.f(name), "review_log")
    for name in ("sense_id", "rating", "applied", "mastery_after", "due_after"):
        op.drop_column("review_log", name)
    for name in ("request_hash", "activity_day", "result"):
        op.alter_column("review_log", name, nullable=False)


def downgrade():
    raise RuntimeError(
        "Batch receipts cannot be downgraded without data loss; "
        "restore a verified pre-upgrade backup"
    )
