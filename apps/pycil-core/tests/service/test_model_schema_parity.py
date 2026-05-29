"""Model ↔ schema structural parity gate.

After the raw-SQL → SQLModel conversion, the 43 `table=True` models must stay
structurally faithful to the live Postgres schema (built by the raw-DDL
migrations). This test runs Alembic's autogenerate comparison against the
migrated test DB and fails if any STRUCTURAL drift exists: a modeled table or
column present in the models but missing from the DB (or vice versa).

Cosmetic differences are intentionally tolerated and NOT failed on:
- `AutoString` (SQLModel's str type) vs reflected `TEXT` — semantically equal.
- Undeclared `server_default` on columns whose value the app always supplies
  (integers/text/json with a Python-side default) — not load-bearing for INSERT.

The load-bearing server defaults (timestamp `now()`, surrogate-PK
`gen_random_uuid()`) ARE declared on the models and are exercised by the
service/integration suite; this gate guards against future model edits that add
or remove a field without a matching migration.
"""
from __future__ import annotations

import shared.db  # noqa: F401  (registers all table models on SQLModel.metadata)
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlmodel import SQLModel

_STRUCTURAL = {"add_table", "remove_table", "add_column", "remove_column"}


def _include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in SQLModel.metadata.tables
    if type_ in ("index", "foreign_key_constraint", "unique_constraint"):
        return False
    return True


def test_models_have_no_structural_drift_vs_schema(_migrate_schema, _pg_dsn) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(_pg_dsn)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                connection=conn,
                opts={
                    "include_object": _include_object,
                    "compare_type": True,
                    "compare_server_default": False,
                },
            )
            diffs = compare_metadata(ctx, SQLModel.metadata)
    finally:
        engine.dispose()

    structural = [d for d in diffs if isinstance(d, tuple) and d and d[0] in _STRUCTURAL]
    assert not structural, f"Model/schema structural drift detected: {structural}"
