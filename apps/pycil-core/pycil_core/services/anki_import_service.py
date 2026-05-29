"""Anki .apkg import/export helpers (P2 phase 3).

Import: graceful best-effort SQLite parse → flat term list. On schema
mismatch we return [] and let the caller surface a friendly "upgrade Anki
and re-export" message.

Export: minimal stdlib-only .apkg builder. Produces a `collection.anki2`
SQLite blob with just enough schema (col + notes + cards) for Anki 2.1.x
to read; round-trips through `parse_anki_apkg` for test coverage.
"""
from __future__ import annotations

import io
import json
import logging
import re
import sqlite3
import tempfile
import time
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from shared.db import DeckTerm, Definition, Term, TermExampleSentence
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlmodel.ext.asyncio.session import AsyncSession

_log = logging.getLogger(__name__)

MAX_NOTES_IMPORT = 2000


@dataclass
class ImportedTerm:
    value: str
    pre_definition: str | None


def parse_anki_apkg(blob: bytes, *, max_rows: int = 5000) -> Sequence[ImportedTerm]:
    """Best-effort .apkg parse → flat term list.

    Uses the embedded `collection.anki2` SQLite. Returns [] on schema
    mismatch — caller decides whether to surface an error.
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


# ---------------------------------------------------------------------------
# Export — minimal stdlib .apkg builder.
# ---------------------------------------------------------------------------

# Anki 2.1.x schema subset. Real Anki has many more columns + JSON config blobs;
# this trims to what's needed for the exported file to round-trip through our
# own parser AND open in Anki desktop. The model/deck IDs are arbitrary.
_ANKI_SCHEMA = """
CREATE TABLE col (
  id              INTEGER PRIMARY KEY,
  crt             INTEGER NOT NULL,
  mod             INTEGER NOT NULL,
  scm             INTEGER NOT NULL,
  ver             INTEGER NOT NULL,
  dty             INTEGER NOT NULL,
  usn             INTEGER NOT NULL,
  ls              INTEGER NOT NULL,
  conf            TEXT NOT NULL,
  models          TEXT NOT NULL,
  decks           TEXT NOT NULL,
  dconf           TEXT NOT NULL,
  tags            TEXT NOT NULL
);
CREATE TABLE notes (
  id              INTEGER PRIMARY KEY,
  guid            TEXT NOT NULL,
  mid             INTEGER NOT NULL,
  mod             INTEGER NOT NULL,
  usn             INTEGER NOT NULL,
  tags            TEXT NOT NULL,
  flds            TEXT NOT NULL,
  sfld            TEXT NOT NULL,
  csum            INTEGER NOT NULL,
  flags           INTEGER NOT NULL,
  data            TEXT NOT NULL
);
CREATE TABLE cards (
  id              INTEGER PRIMARY KEY,
  nid             INTEGER NOT NULL,
  did             INTEGER NOT NULL,
  ord             INTEGER NOT NULL,
  mod             INTEGER NOT NULL,
  usn             INTEGER NOT NULL,
  type            INTEGER NOT NULL,
  queue           INTEGER NOT NULL,
  due             INTEGER NOT NULL,
  ivl             INTEGER NOT NULL,
  factor          INTEGER NOT NULL,
  reps            INTEGER NOT NULL,
  lapses          INTEGER NOT NULL,
  left            INTEGER NOT NULL,
  odue            INTEGER NOT NULL,
  odid            INTEGER NOT NULL,
  flags           INTEGER NOT NULL,
  data            TEXT NOT NULL
);
CREATE INDEX ix_notes_csum ON notes (csum);
CREATE INDEX ix_cards_nid ON cards (nid);
"""


_MODEL_ID = 1607392319000
_DECK_ID = 1
_DEFAULT_DECK = {
    "1": {
        "id": _DECK_ID,
        "name": "Pycil Export",
        "extendRev": 50,
        "usn": 0,
        "collapsed": False,
        "newToday": [0, 0],
        "revToday": [0, 0],
        "lrnToday": [0, 0],
        "timeToday": [0, 0],
        "dyn": 0,
        "extendNew": 10,
        "conf": 1,
        "desc": "",
        "mod": 0,
    }
}
_DEFAULT_MODELS = {
    str(_MODEL_ID): {
        "id": _MODEL_ID,
        "name": "Pycil Basic",
        "type": 0,
        "mod": 0,
        "usn": 0,
        "sortf": 0,
        "did": _DECK_ID,
        "tmpls": [
            {
                "name": "Card 1",
                "ord": 0,
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
                "did": None,
                "bqfmt": "",
                "bafmt": "",
            }
        ],
        "flds": [
            {"name": "Front", "ord": 0, "sticky": False, "rtl": False,
             "font": "Arial", "size": 20, "media": []},
            {"name": "Back", "ord": 1, "sticky": False, "rtl": False,
             "font": "Arial", "size": 20, "media": []},
        ],
        "css": ".card{font-family:arial;font-size:20px;text-align:center}",
        "latexPre": "",
        "latexPost": "",
        "req": [[0, "any", [0]]],
        "tags": [],
        "vers": [],
    }
}


def _checksum(field0: str) -> int:
    """Anki uses first 8 hex chars of SHA1(first_field) as int."""
    import hashlib

    h = hashlib.sha1(field0.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _format_back(definition: str | None, examples: Iterable[str]) -> str:
    parts: list[str] = []
    if definition:
        parts.append(definition)
    examples_list = [e for e in examples if e]
    if examples_list:
        parts.append("<br><br>" + "<br>".join(f"• {e}" for e in examples_list))
    return "".join(parts)


def build_apkg(notes: Sequence[tuple[str, str | None, list[str]]]) -> bytes:
    """Build a minimal `.apkg` from (front, back_definition, examples) tuples.

    Returns the raw zipped bytes. `back_definition` may be None; `examples`
    may be empty. The caller is responsible for trimming to a sane note count.
    """
    now = int(time.time())
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        conn = sqlite3.connect(tmp_path)
        try:
            conn.executescript(_ANKI_SCHEMA)
            conn.execute(
                "INSERT INTO col VALUES (1,?,?,?,11,0,0,0,?,?,?,?,?)",
                (
                    now,
                    now * 1000,
                    now * 1000,
                    "{}",
                    json.dumps(_DEFAULT_MODELS),
                    json.dumps(_DEFAULT_DECK),
                    "{}",
                    "{}",
                ),
            )
            for i, (front, back, examples) in enumerate(notes, start=1):
                front_clean = front.strip()
                if not front_clean:
                    continue
                back_html = _format_back(back, examples)
                flds = front_clean + "\x1f" + back_html
                conn.execute(
                    "INSERT INTO notes VALUES (?,?,?,?,-1,'',?,?,?,0,'')",
                    (
                        i,
                        f"pycil-{i:08x}",
                        _MODEL_ID,
                        now,
                        flds,
                        front_clean,
                        _checksum(front_clean),
                    ),
                )
                conn.execute(
                    "INSERT INTO cards VALUES (?,?,?,0,?,-1,0,0,?,0,0,0,0,0,0,0,0,'')",
                    (i, i, _DECK_ID, now, i),
                )
            conn.commit()
        finally:
            conn.close()

        with open(tmp_path, "rb") as f:
            db_bytes = f.read()
    finally:
        try:
            import os

            os.unlink(tmp_path)
        except OSError:
            pass

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("collection.anki2", db_bytes)
        zf.writestr("media", "{}")
    return out.getvalue()


async def fetch_deck_notes_for_export(
    session: AsyncSession, deck_id: UUID
) -> list[tuple[str, str | None, list[str]]]:
    """Returns (term, canonical_meaning, examples) tuples for a deck."""
    examples_subquery = (
        select(
            func.array_agg(
                aggregate_order_by(
                    TermExampleSentence.value,
                    TermExampleSentence.id.asc(),
                )
            )
        )
        .where(TermExampleSentence.definition_id == Definition.id)
        .scalar_subquery()
    )
    stmt = (
        select(
            Term.value.label("term"),
            Definition.canonical_meaning.label("definition"),
            examples_subquery.label("examples"),
        )
        .select_from(DeckTerm)
        .join(Term, Term.id == DeckTerm.term_id)
        .outerjoin(Definition, Definition.term_id == Term.id)
        .where(DeckTerm.deck_id == deck_id)
        .order_by(DeckTerm.position.asc())
    )
    rows = (await session.exec(stmt)).all()
    return [(r.term, r.definition, list(r.examples or [])) for r in rows]
