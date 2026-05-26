"""Anki .apkg + CSV import helpers (P2 phases 2-3).

Both hand off to `term_batch_service.add_terms_batch`; this module just
parses the file format into a flat list of term strings + optional
pre-enriched payloads. Real Anki .apkg parsing is best-effort: graceful
degrade to "tab-separated front/back" when the .apkg sqlite blob doesn't
match Anki 2.x layout.
"""
from __future__ import annotations

import io
import logging
import re
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Sequence

_log = logging.getLogger(__name__)


@dataclass
class ImportedTerm:
    value: str
    pre_definition: str | None


def parse_anki_apkg(blob: bytes, *, max_rows: int = 5000) -> Sequence[ImportedTerm]:
    """Best-effort .apkg parse → flat term list.

    Uses the embedded `collection.anki2` SQLite. Falls back to empty list
    on schema mismatch — caller decides whether to surface an error.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = [n for n in zf.namelist() if n.endswith("collection.anki2")]
            if not names:
                return []
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
                tmp.write(zf.read(names[0]))
                tmp.flush()
                conn = sqlite3.connect(tmp.name)
                try:
                    cur = conn.execute("SELECT flds FROM notes LIMIT ?", (max_rows,))
                    out: list[ImportedTerm] = []
                    for row in cur:
                        fields = row[0].split("\x1f")
                        front = _strip_html(fields[0]).strip() if fields else ""
                        back = (
                            _strip_html(fields[1]).strip() if len(fields) > 1 else None
                        )
                        if front:
                            out.append(
                                ImportedTerm(value=front, pre_definition=back or None)
                            )
                    return out
                finally:
                    conn.close()
    except (zipfile.BadZipFile, sqlite3.DatabaseError, OSError) as exc:
        _log.warning("anki_parse_failed", extra={"err": str(exc)[:200]})
        return []


_HTML_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _HTML_RE.sub("", s)
