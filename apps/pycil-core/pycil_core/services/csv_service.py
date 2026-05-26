"""CSV import + export helpers (P2 phase 2).

Parse policy:
- Required column: `term`. Missing → 422.
- Optional columns (case-insensitive): `definition`, `synonyms`, `antonyms`,
  `examples`. Multi-value columns split on `;` or `|`. Trimmed; empty → None.
- Rows with empty `term` are silently skipped — keeps copy-pasted spreadsheets
  with trailing blanks importable.
- BOM (Excel UTF-8) handled via `utf-8-sig`.
- Hard-cap rows at MAX_ROWS to bound memory; cap is enforced by the route on
  raw bytes BEFORE we get here.

User-provided definitions are NEVER written to the canonical `definitions`
row — they go to `definition_overrides(user_id, term_id, payload)` so a
malicious importer can't pollute the global term cache for other users.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024


@dataclass
class CsvTermRow:
    value: str
    definition: str | None = None
    synonyms: list[str] | None = None
    antonyms: list[str] | None = None
    examples: list[str] | None = None

    @property
    def is_pre_enriched(self) -> bool:
        return any(
            (self.definition, self.synonyms, self.antonyms, self.examples)
        )

    def override_payload(self) -> dict:
        return {
            "definition": self.definition,
            "synonyms": self.synonyms or [],
            "antonyms": self.antonyms or [],
            "examples": self.examples or [],
        }


_LIST_SPLIT_RE = re.compile(r"\s*[;|]\s*")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _sanitize(value: str | None) -> str | None:
    """Strip HTML tags, control chars, surrounding whitespace; cap at 2KB."""
    if value is None:
        return None
    cleaned = _HTML_TAG_RE.sub("", value)
    cleaned = _CONTROL_RE.sub("", cleaned).strip()
    return cleaned[:2000] if cleaned else None


def _split_list(value: str | None) -> list[str] | None:
    sanitized = _sanitize(value)
    if not sanitized:
        return None
    parts = [p.strip() for p in _LIST_SPLIT_RE.split(sanitized) if p.strip()]
    return parts or None


def parse_csv(raw_bytes: bytes) -> tuple[list[CsvTermRow], list[str]]:
    """Returns (rows, fieldnames). Raises ValueError on malformed UTF-8 or
    missing `term` column. Caller turns the ValueError into a 422."""
    try:
        text_data = raw_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("csv_invalid_utf8") from exc

    reader = csv.DictReader(io.StringIO(text_data))
    if not reader.fieldnames:
        raise ValueError("csv_empty")

    # Case-insensitive column lookup; build a {lower_key: original_key} map.
    lower = {f.lower().strip(): f for f in reader.fieldnames}
    if "term" not in lower:
        raise ValueError("csv_missing_term_column")

    out: list[CsvTermRow] = []
    for row in reader:
        raw_term = row.get(lower["term"]) or ""
        value = _sanitize(raw_term)
        if not value:
            continue
        out.append(
            CsvTermRow(
                value=value,
                definition=_sanitize(row.get(lower.get("definition", ""), None)),
                synonyms=_split_list(row.get(lower.get("synonyms", ""), None)),
                antonyms=_split_list(row.get(lower.get("antonyms", ""), None)),
                examples=_split_list(row.get(lower.get("examples", ""), None)),
            )
        )
    return out, list(reader.fieldnames)


async def store_overrides(
    session: AsyncSession,
    user_id: UUID,
    term_value_to_id: dict[str, int],
    rows: list[CsvTermRow],
) -> int:
    """Upsert per-user definition overrides for pre-enriched rows.

    `term_value_to_id` is the {value: term.id} map after `add_terms_batch`
    has reconciled the global terms table.
    """
    written = 0
    for row in rows:
        if not row.is_pre_enriched:
            continue
        term_id = term_value_to_id.get(row.value)
        if term_id is None:
            continue
        await session.execute(
            text(
                """
                INSERT INTO definition_overrides (user_id, term_id, payload)
                VALUES (:uid, :tid, CAST(:payload AS jsonb))
                ON CONFLICT (user_id, term_id) DO UPDATE
                  SET payload = EXCLUDED.payload, updated_at = NOW()
                """
            ),
            {
                "uid": user_id,
                "tid": term_id,
                "payload": json.dumps(row.override_payload()),
            },
        )
        written += 1
    if written:
        await session.commit()
    return written


def _csv_escape_cell(cell: str | None) -> str:
    """Prefix Excel-formula-trigger characters with a single quote."""
    if cell is None:
        return ""
    if cell and cell[0] in ("=", "+", "-", "@"):
        return "'" + cell
    return cell


async def stream_export(
    session: AsyncSession, deck_id: UUID
) -> AsyncIterator[str]:
    """Yields header + per-term CSV rows. Caller wraps in StreamingResponse."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["term", "definition", "synonyms", "antonyms", "examples"])
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate()

    rows = (
        await session.execute(
            text(
                """
                SELECT t.value AS term,
                       d.canonical_meaning AS definition,
                       d.synonyms, d.antonyms,
                       ARRAY(
                         SELECT value FROM term_example_sentences
                          WHERE definition_id = d.id ORDER BY id
                       ) AS examples
                  FROM deck_terms dt
                  JOIN terms t ON t.id = dt.term_id
             LEFT JOIN definitions d ON d.term_id = t.id
                 WHERE dt.deck_id = :deck
                 ORDER BY dt.position
                """
            ),
            {"deck": deck_id},
        )
    ).all()
    for r in rows:
        writer.writerow(
            [
                _csv_escape_cell(r.term),
                _csv_escape_cell(r.definition or ""),
                "; ".join(r.synonyms or []),
                "; ".join(r.antonyms or []),
                " | ".join(r.examples or []),
            ]
        )
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
