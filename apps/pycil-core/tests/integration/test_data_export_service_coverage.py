"""Direct unit coverage for data_export_service.

Drives `export()` (an AsyncIterator[bytes] of NDJSON) and asserts:
- the `_meta` header row,
- profile + nodes rows are present and serialized (UUID/datetime/enum → JSON),
- the per-table error branch emits an `_error` row instead of aborting,
- `_serialize` handles nested dict/list/date/UUID/Enum.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import text

from pycil_core.services import data_export_service as des


async def _collect(session, user_id) -> list[dict]:
    chunks: list[bytes] = []
    async for b in des.export(session, user_id):
        chunks.append(b)
    text_blob = b"".join(chunks).decode()
    return [json.loads(line) for line in text_blob.splitlines() if line.strip()]


async def test_export_emits_meta_header(session, test_user) -> None:
    rows = await _collect(session, UUID(str(test_user["id"])))
    assert rows[0]["_meta"]["version"] == 1
    assert rows[0]["_meta"]["user_id"] == str(test_user["id"])


async def test_export_includes_profile_and_nodes(session, test_user) -> None:
    # Give the user a deck so the `nodes` table yields a row.
    await session.execute(
        text(
            "INSERT INTO nodes (author_id, type, name, visibility) "
            "VALUES (:a, 'DECK'::node_type, 'Exported', 'PRIVATE'::visibility)"
        ),
        {"a": test_user["id"]},
    )
    await session.commit()

    rows = await _collect(session, UUID(str(test_user["id"])))
    tables = {r.get("_table") for r in rows if "_table" in r}
    assert "profile" in tables
    assert "nodes" in tables

    profile_rows = [r for r in rows if r.get("_table") == "profile"]
    assert len(profile_rows) == 1
    # UUID serialized to string, role enum to its value.
    assert profile_rows[0]["row"]["id"] == str(test_user["id"])

    node_rows = [r for r in rows if r.get("_table") == "nodes"]
    assert len(node_rows) == 1
    assert node_rows[0]["row"]["name"] == "Exported"


async def test_export_does_not_leak_other_users_rows(
    session, test_user, second_user
) -> None:
    await session.execute(
        text(
            "INSERT INTO nodes (author_id, type, name, visibility) "
            "VALUES (:a, 'DECK'::node_type, 'Theirs', 'PRIVATE'::visibility)"
        ),
        {"a": second_user["id"]},
    )
    await session.commit()
    rows = await _collect(session, UUID(str(test_user["id"])))
    node_rows = [r for r in rows if r.get("_table") == "nodes"]
    assert node_rows == []  # only the export target's nodes


async def test_export_error_branch_emits_error_row(session, test_user, monkeypatch) -> None:
    """A query that raises must yield an `_error` row, not abort the stream."""
    bad_tables = list(des._TABLES_FOR_USER)
    # Reference a non-existent table via a raw-SQL entry.
    bad_tables.append(("broken", "SELECT * FROM does_not_exist WHERE x = :uid"))
    monkeypatch.setattr(des, "_TABLES_FOR_USER", bad_tables)

    rows = await _collect(session, UUID(str(test_user["id"])))
    error_rows = [r for r in rows if r.get("_table") == "broken"]
    assert len(error_rows) == 1
    assert "_error" in error_rows[0]
    # Stream still completed (meta header present).
    assert rows[0]["_meta"]["version"] == 1


# ── _serialize unit cases ────────────────────────────────────────────────────


class _Color(Enum):
    RED = "red"


def test_serialize_primitives_and_containers() -> None:
    uid = uuid4()
    out = des._serialize(
        {
            "u": uid,
            "d": date(2024, 1, 2),
            "dt": datetime(2024, 1, 2, 3, 4, 5),
            "e": _Color.RED,
            "nested": [1, {"x": uid}],
            "plain": "str",
            "n": 7,
        }
    )
    assert out["u"] == str(uid)
    assert out["d"] == "2024-01-02"
    assert out["dt"].startswith("2024-01-02T03:04:05")
    assert out["e"] == "red"
    assert out["nested"][1]["x"] == str(uid)
    assert out["plain"] == "str"
    assert out["n"] == 7
