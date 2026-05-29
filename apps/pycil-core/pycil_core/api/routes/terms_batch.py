"""Bulk + CSV term ingestion routes (P2 phases 1-2)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from shared.db import Node, Term
from sqlmodel import select

from pycil_core.api.deps import RedisDep, SessionDep, UserDep
from pycil_core.services import csv_service
from pycil_core.services.term_batch_service import (
    MAX_BATCH_SIZE,
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
    raw = await file.read(csv_service.MAX_BYTES + 1)
    if len(raw) > csv_service.MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "csv_too_large"
        )
    try:
        rows, _fields = csv_service.parse_csv(raw)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)
        ) from exc
    if len(rows) > csv_service.MAX_ROWS:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "csv_too_many_rows"
        )

    values = [row.value for row in rows]
    result = await add_terms_batch(
        session, redis, user.id, deck_id, values, source="csv"
    )

    if any(row.is_pre_enriched for row in rows):
        accepted_values = {
            o.value for o in result.outcomes if o.status in ("created", "existing")
        }
        if accepted_values:
            id_rows = (
                await session.exec(
                    select(Term.id, Term.value).where(Term.value.in_(list(accepted_values)))
                )
            ).all()
            value_to_id = {r.value: r.id for r in id_rows}
            await csv_service.store_overrides(session, user.id, value_to_id, rows)

    return _to_response(result)


@router.get("/{deck_id}/export.csv")
async def csv_export(
    deck_id: UUID,
    user: UserDep,
    session: SessionDep,
):
    from fastapi.responses import StreamingResponse

    deck_row = (await session.exec(select(Node.author_id).where(Node.id == deck_id))).first()
    if not deck_row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deck_not_found")
    if deck_row != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "deck_forbidden")

    return StreamingResponse(
        csv_service.stream_export(session, deck_id),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="deck-{deck_id}.csv"'},
    )
