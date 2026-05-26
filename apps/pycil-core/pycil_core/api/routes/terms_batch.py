"""Bulk + CSV term ingestion routes (P2 phases 1-2)."""
from __future__ import annotations

import csv
import io
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from pycil_core.api.deps import RedisDep, SessionDep, UserDep
from pycil_core.services.term_batch_service import (
    MAX_BATCH_SIZE,
    BatchOutcome,
    BatchResult,
    add_terms_batch,
)

router = APIRouter(prefix="/decks", tags=["terms-batch"])


class BulkAddRequest(BaseModel):
    values: list[str] = Field(..., min_length=1, max_length=MAX_BATCH_SIZE)
    source: str = Field(default="bulk_paste")


class BatchResponse(BaseModel):
    accepted: int
    deduped: int
    rejected: int
    job_ids: list[str]
    outcomes: list[dict]


def _to_response(result: BatchResult) -> BatchResponse:
    return BatchResponse(
        accepted=result.accepted,
        deduped=result.deduped,
        rejected=result.rejected,
        job_ids=result.job_ids,
        outcomes=[
            {
                "value": o.value,
                "status": o.status,
                "job_id": o.job_id,
                "error": o.error,
            }
            for o in result.outcomes
        ],
    )


@router.post(
    "/{deck_id}/terms/batch",
    response_model=BatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def batch_add(
    deck_id: UUID,
    payload: BulkAddRequest,
    user: UserDep,
    session: SessionDep,
    redis: RedisDep,
) -> BatchResponse:
    result = await add_terms_batch(
        session,
        redis,
        user.id,
        deck_id,
        payload.values,
        source=payload.source,  # type: ignore[arg-type]
    )
    return _to_response(result)


_CSV_MAX_BYTES = 5 * 1024 * 1024
_CSV_MAX_ROWS = 5000


@router.post(
    "/{deck_id}/terms/csv",
    response_model=BatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def csv_import(
    deck_id: UUID,
    user: UserDep,
    session: SessionDep,
    redis: RedisDep,
    file: Annotated[UploadFile, File()],
) -> BatchResponse:
    raw = await file.read(_CSV_MAX_BYTES + 1)
    if len(raw) > _CSV_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "csv_too_large"
        )
    text_data = raw.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(text_data))
    if not reader.fieldnames or "term" not in {f.lower() for f in reader.fieldnames}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "csv_missing_term_column"
        )
    rows = list(reader)
    if len(rows) > _CSV_MAX_ROWS:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "csv_too_many_rows")

    values = [
        (row.get("term") or row.get("Term") or "").strip()
        for row in rows
        if (row.get("term") or row.get("Term"))
    ]
    result = await add_terms_batch(
        session, redis, user.id, deck_id, values, source="csv"
    )
    return _to_response(result)


def _csv_escape_cell(cell: str | None) -> str:
    if cell is None:
        return ""
    if cell and cell[0] in ("=", "+", "-", "@"):
        return "'" + cell
    return cell


@router.get("/{deck_id}/export.csv")
async def csv_export(
    deck_id: UUID,
    user: UserDep,
    session: SessionDep,
):
    from fastapi.responses import StreamingResponse

    deck_row = (
        await session.execute(
            text("SELECT author_id FROM nodes WHERE id = :id"),
            {"id": deck_id},
        )
    ).first()
    if not deck_row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deck_not_found")
    if deck_row.author_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "deck_forbidden")

    async def gen():
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

    return StreamingResponse(
        gen(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="deck-{deck_id}.csv"'},
    )
