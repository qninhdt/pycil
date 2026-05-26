"""Anki .apkg import + export routes (P2 phase 3)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import text

from pycil_core.api.deps import RedisDep, SessionDep, UserDep
from pycil_core.api.routes.terms_batch import BatchResponse, _to_response
from pycil_core.services import anki_import_service
from pycil_core.services.term_batch_service import add_terms_batch

router = APIRouter(prefix="/decks", tags=["anki"])

_APKG_MAX_BYTES = 50 * 1024 * 1024


@router.post(
    "/{deck_id}/terms/anki",
    response_model=BatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def anki_import(
    deck_id: UUID,
    user: UserDep,
    session: SessionDep,
    redis: RedisDep,
    file: Annotated[UploadFile, File()],
) -> BatchResponse:
    raw = await file.read(_APKG_MAX_BYTES + 1)
    if len(raw) > _APKG_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "apkg_too_large"
        )

    notes = anki_import_service.parse_anki_apkg(
        raw, max_rows=anki_import_service.MAX_NOTES_IMPORT
    )
    if not notes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "apkg_no_notes_found"
        )
    if len(notes) > anki_import_service.MAX_NOTES_IMPORT:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "apkg_too_many_notes"
        )

    values = [n.value for n in notes]
    result = await add_terms_batch(
        session, redis, user.id, deck_id, values, source="anki"
    )
    return _to_response(result)


@router.get("/{deck_id}/export.apkg")
async def anki_export(
    deck_id: UUID,
    user: UserDep,
    session: SessionDep,
):
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

    notes = await anki_import_service.fetch_deck_notes_for_export(session, deck_id)
    blob = anki_import_service.build_apkg(notes)
    return Response(
        content=blob,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="deck-{deck_id}.apkg"'
        },
    )
