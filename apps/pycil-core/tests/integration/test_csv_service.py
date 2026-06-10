"""CSV import + export pinned tests (P2 phase 2).

Service-level (pure parser):
  - empty CSV (no header) → ValueError csv_empty
  - missing required `term` column → ValueError csv_missing_term_column
  - malformed UTF-8 → ValueError csv_invalid_utf8
  - Excel BOM handled (utf-8-sig)
  - pre-enriched columns parsed; list-fields split on `;` / `|`
  - HTML tags stripped from cell values

Integration (end-to-end through add_terms_batch + store_overrides):
  - pre-enriched rows → definition_overrides upserted, jobs still enqueued
    (canonical enrichment runs per cache miss; user-supplied stays
    user-scoped to avoid polluting global terms table)
  - term-only rows → enqueue per fresh value
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from pycil_core.services import csv_service, term_batch_service
from tests.factories import make_deck


# ---------------------------------------------------------------------------
# parse_csv (no DB)
# ---------------------------------------------------------------------------

def test_empty_csv_raises() -> None:
    with pytest.raises(ValueError, match="csv_empty"):
        csv_service.parse_csv(b"")


def test_missing_term_column_raises() -> None:
    with pytest.raises(ValueError, match="csv_missing_term_column"):
        csv_service.parse_csv(b"foo,bar\nalpha,beta\n")


def test_malformed_utf8_raises() -> None:
    with pytest.raises(ValueError, match="csv_invalid_utf8"):
        # \xff is not a valid leading byte in UTF-8.
        csv_service.parse_csv(b"term\n\xff\xfe garbage\n")


def test_bom_handled() -> None:
    # Excel exports UTF-8 with BOM.
    raw = "﻿term,definition\nresilience,bouncing back\n".encode("utf-8")
    rows, fields = csv_service.parse_csv(raw)
    assert fields == ["term", "definition"]
    assert len(rows) == 1
    assert rows[0].value == "resilience"
    assert rows[0].definition == "bouncing back"


def test_pre_enriched_columns_split() -> None:
    raw = (
        b"term,definition,synonyms,antonyms,examples\n"
        b"prudent,careful and sensible,wise; cautious,reckless | rash,"
        b"He was prudent with money | A prudent decision\n"
    )
    rows, _ = csv_service.parse_csv(raw)
    assert rows[0].definition == "careful and sensible"
    assert rows[0].synonyms == ["wise", "cautious"]
    assert rows[0].antonyms == ["reckless", "rash"]
    assert rows[0].examples == [
        "He was prudent with money",
        "A prudent decision",
    ]
    assert rows[0].is_pre_enriched


def test_html_stripped_from_cells() -> None:
    raw = (
        b"term,definition\n"
        b"<b>brave</b>,<i>showing courage</i>\n"
    )
    rows, _ = csv_service.parse_csv(raw)
    assert rows[0].value == "brave"
    assert rows[0].definition == "showing courage"


def test_blank_term_rows_skipped() -> None:
    raw = b"term,definition\nalpha,a\n,nothing\nbeta,b\n"
    rows, _ = csv_service.parse_csv(raw)
    assert [r.value for r in rows] == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# Integration with add_terms_batch + store_overrides.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _budget_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BUDGET_DAILY_USD", "20")


@pytest.fixture
def _enqueue_mock(monkeypatch):
    calls: list[dict] = []

    async def fake(job_name, *args, _job_id):
        calls.append({"name": job_name, "args": args, "job_id": _job_id})

    monkeypatch.setattr(
        "pycil_core.services.job_service.enqueue_arq_job", fake
    )
    monkeypatch.setattr(
        "pycil_core.services._job_enqueue.enqueue_arq_job", fake
    )
    return calls


async def test_pre_enriched_writes_definition_overrides(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    """User-supplied definition lands in `definition_overrides` (per-user),
    NOT in the canonical `definitions` table — protects the global cache."""
    deck = await make_deck(session, author_id=test_user["id"])
    raw = (
        b"term,definition,synonyms\n"
        b"meticulous,very careful and precise,thorough; careful\n"
    )
    rows, _ = csv_service.parse_csv(raw)
    values = [r.value for r in rows]

    result = await term_batch_service.add_terms_batch(
        session, fakeredis_client, test_user["id"], deck["id"], values, source="csv"
    )

    id_rows = (
        await session.execute(
            text("SELECT id, value FROM terms WHERE value = ANY(:vals)"),
            {"vals": values},
        )
    ).all()
    value_to_id = {r.value: r.id for r in id_rows}
    written = await csv_service.store_overrides(
        session, test_user["id"], value_to_id, rows
    )

    assert written == 1
    override = (
        await session.execute(
            text(
                "SELECT payload FROM definition_overrides "
                "WHERE user_id = :uid AND term_id = :tid"
            ),
            {"uid": test_user["id"], "tid": value_to_id["meticulous"]},
        )
    ).one()
    payload = override.payload if isinstance(override.payload, dict) else json.loads(
        override.payload
    )
    assert payload["definition"] == "very careful and precise"
    assert payload["synonyms"] == ["thorough", "careful"]

    canonical = (
        await session.execute(
            text("SELECT id FROM definitions WHERE term_id = :tid"),
            {"tid": value_to_id["meticulous"]},
        )
    ).first()
    assert canonical is None
    assert result.accepted == 1
    assert len(_enqueue_mock) == 1


async def test_term_only_csv_enqueues_jobs(
    session, fakeredis_client, test_user, _enqueue_mock
) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    raw = b"term\nfortitude\nresilience\nperseverance\n"
    rows, _ = csv_service.parse_csv(raw)
    values = [r.value for r in rows]

    result = await term_batch_service.add_terms_batch(
        session, fakeredis_client, test_user["id"], deck["id"], values, source="csv"
    )
    assert result.accepted == 3
    assert len(_enqueue_mock) == 3
