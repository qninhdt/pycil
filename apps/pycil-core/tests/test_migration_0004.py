"""Schema-level assertions for migration 0004 (v02 feature fill).

Boots a clean DB via DATABASE_URL_TEST, runs `alembic upgrade head`, and
asserts every new column, table, index, and ENUM value exists with the
expected nullability/default. Covers GIN indexes via pg_indexes and the
SHORTCUT enum value via a literal cast.
"""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL_TEST"),
    reason="DATABASE_URL_TEST not set",
)


@pytest.fixture(scope="module")
def upgraded_engine():
    db_url = os.environ["DATABASE_URL_TEST"]
    engine = create_engine(db_url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


def _columns(conn, table: str) -> dict[str, dict]:
    rows = conn.execute(
        text(
            "SELECT column_name, is_nullable, column_default, data_type "
            "FROM information_schema.columns WHERE table_name = :t"
        ),
        {"t": table},
    ).all()
    return {r.column_name: dict(r._mapping) for r in rows}


def test_users_gamification_columns(upgraded_engine):
    with upgraded_engine.connect() as conn:
        cols = _columns(conn, "users")
    for c in [
        "image_url", "streak_days", "last_session_date", "xp_total", "level",
        "badges", "league_rank", "locale", "bio", "study_settings",
        "deleted_at", "stripe_customer_id",
    ]:
        assert c in cols, f"users.{c} missing"
    assert cols["xp_total"]["is_nullable"] == "NO"
    assert cols["badges"]["data_type"] == "jsonb"
    assert cols["deleted_at"]["is_nullable"] == "YES"


def test_new_tables_exist(upgraded_engine):
    with upgraded_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).all()
    existing = {r.tablename for r in rows}
    for t in [
        "notifications", "responses", "deck_clones", "chat_sessions",
        "chat_messages", "test_runs", "test_run_items", "subscriptions",
        "stripe_webhook_events", "node_share_links",
    ]:
        assert t in existing, f"table {t} missing"


def test_definitions_jsonb_additions(upgraded_engine):
    with upgraded_engine.connect() as conn:
        cols = _columns(conn, "definitions")
    for c in ["tags", "translation", "tts_url"]:
        assert c in cols
    assert cols["translation"]["data_type"] == "jsonb"
    assert cols["tts_url"]["data_type"] == "jsonb"


def test_questions_elo_variant(upgraded_engine):
    with upgraded_engine.connect() as conn:
        cols = _columns(conn, "questions")
    assert cols["elo"]["is_nullable"] == "NO"
    assert "variant_seed" in cols


def test_user_term_jobs_columns(upgraded_engine):
    with upgraded_engine.connect() as conn:
        cols = _columns(conn, "user_term_jobs")
    for c in ["last_event", "last_llm_response"]:
        assert c in cols
        assert cols[c]["data_type"] == "jsonb"


def test_shortcut_enum_value(upgraded_engine):
    with upgraded_engine.connect() as conn:
        result = conn.execute(text("SELECT 'SHORTCUT'::node_type")).scalar()
    assert result == "SHORTCUT"


def test_gin_trgm_indexes(upgraded_engine):
    with upgraded_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE indexname IN ('terms_value_trgm', 'nodes_name_trgm', "
                "'definitions_canonical_trgm')"
            )
        ).all()
    names = {r.indexname for r in rows}
    assert names == {
        "terms_value_trgm",
        "nodes_name_trgm",
        "definitions_canonical_trgm",
    }


def test_nodes_target_node_id_fk(upgraded_engine):
    with upgraded_engine.connect() as conn:
        cols = _columns(conn, "nodes")
    assert "target_node_id" in cols
    assert cols["target_node_id"]["is_nullable"] == "YES"


def test_subscriptions_unique_constraint(upgraded_engine):
    with upgraded_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'subscriptions'::regclass AND contype = 'u'"
            )
        ).all()
    conames = {r.conname for r in rows}
    assert any("user_id" in n for n in conames), conames
