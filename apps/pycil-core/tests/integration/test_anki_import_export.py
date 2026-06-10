"""Anki .apkg import + export pinned tests (P2 phase 3).

We don't ship a committed binary fixture — we generate `.apkg` blobs in-memory
via `build_apkg`, then run them through `parse_anki_apkg`. This validates that
our exporter and importer agree on the schema; round-tripping through Anki
desktop is verified manually (documented in the phase plan).

Pinned:
- Round-trip: build_apkg → parse_anki_apkg returns the same terms.
- Empty `.apkg` (no `collection.anki2`) → returns [] (caller renders 422).
- Malformed zip → returns [] (graceful degrade).
- HTML stripped from the back field on import.
- Cap respected: max_rows truncates at the requested limit.
- Build with empty deck → still produces a valid zip with a header row only.
"""
from __future__ import annotations

import io
import zipfile

from pycil_core.services import anki_import_service


def test_round_trip_basic() -> None:
    notes = [
        ("resilience", "the ability to bounce back", ["She showed resilience."]),
        ("prudent", "careful and sensible", []),
        ("perseverance", None, ["Through perseverance, she succeeded."]),
    ]
    blob = anki_import_service.build_apkg(notes)
    parsed = list(anki_import_service.parse_anki_apkg(blob))

    assert [t.value for t in parsed] == ["resilience", "prudent", "perseverance"]
    # First note has both definition AND example — back field combines them.
    assert parsed[0].pre_definition is not None
    assert "bounce back" in parsed[0].pre_definition
    assert "She showed resilience" in parsed[0].pre_definition
    # Second note has definition only.
    assert parsed[1].pre_definition == "careful and sensible"
    # Third note has example only — back is the example bullet.
    assert parsed[2].pre_definition is not None
    assert "perseverance" in parsed[2].pre_definition.lower()


def test_apkg_without_collection_returns_empty() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("media", "{}")
    parsed = anki_import_service.parse_anki_apkg(out.getvalue())
    assert list(parsed) == []


def test_malformed_zip_returns_empty() -> None:
    parsed = anki_import_service.parse_anki_apkg(b"not a zip at all")
    assert list(parsed) == []


def test_html_stripped_from_back() -> None:
    """Anki cards often contain inline <b>, <i>, <img> — those must not leak
    into our pre_definition payload."""
    notes = [
        ("brave", "<b>showing courage</b> in the face of <i>danger</i>", []),
    ]
    blob = anki_import_service.build_apkg(notes)
    parsed = list(anki_import_service.parse_anki_apkg(blob))
    assert parsed[0].pre_definition == "showing courage in the face of danger"


def test_max_rows_truncates() -> None:
    notes = [(f"term-{i}", f"def-{i}", []) for i in range(10)]
    blob = anki_import_service.build_apkg(notes)
    parsed = list(anki_import_service.parse_anki_apkg(blob, max_rows=3))
    assert len(parsed) == 3
    assert [t.value for t in parsed] == ["term-0", "term-1", "term-2"]


def test_empty_deck_export_still_valid() -> None:
    blob = anki_import_service.build_apkg([])
    # Zip is well-formed and parses to no notes.
    parsed = list(anki_import_service.parse_anki_apkg(blob))
    assert parsed == []
    # Verify the zip really contains a collection.anki2.
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert "collection.anki2" in zf.namelist()
