"""Translation + TTS pipelines (skeleton).

Both are user-triggered worker jobs caching results in JSONB columns:
- definitions.translation : {lang_code: text}
- definitions.tts_url     : {lang_code: signed_url}

Routes are defined here; actual worker jobs (translate_definition,
tts_render) live in apps/worker. v0.2 ships the BE seam; FE buttons +
worker code follow.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from shared.db import DeckDefinition, Definition, Job, Node
from sqlalchemy import select

from pycil_core.api.deps import SessionDep, UserDep

router = APIRouter(prefix="/definitions", tags=["translate-tts"])

_SUPPORTED_LANGS = {"en", "vi", "ja", "ko", "es", "fr", "de"}


async def _assert_owner(session, *, definition_id: int, user_id) -> None:
    row = (
        await session.exec(
            select(Definition.id)
            .join(DeckDefinition, DeckDefinition.definition_id == Definition.id)
            .join(Node, Node.id == DeckDefinition.deck_id)
            .where(Definition.id == definition_id, Node.author_id == user_id)
            .limit(1)
        )
    ).first()
    if not row:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_owner")


@router.post("/{definition_id}/translate")
async def translate(
    definition_id: int,
    user: UserDep,
    session: SessionDep,
    lang: str = Query(...),
) -> dict:
    if lang not in _SUPPORTED_LANGS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_lang")
    await _assert_owner(session, definition_id=definition_id, user_id=user.id)
    cached = (
        await session.exec(
            select(Definition.translation[lang].astext.label("t")).where(
                Definition.id == definition_id
            )
        )
    ).first()
    if cached and cached.t is not None:
        return {"cached": True, "translation": cached.t}
    job = Job(
        type="translate_definition",
        status="queued",
        payload={"definition_id": definition_id, "lang": lang},
        created_by_user_id=user.id,
    )
    session.add(job)
    await session.flush()
    await session.commit()
    return {"cached": False, "job_id": str(job.id)}


@router.post("/{definition_id}/tts")
async def tts(
    definition_id: int,
    user: UserDep,
    session: SessionDep,
    lang: str = Query(default="en"),
) -> dict:
    if lang not in _SUPPORTED_LANGS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_lang")
    await _assert_owner(session, definition_id=definition_id, user_id=user.id)
    cached = (
        await session.exec(
            select(Definition.tts_url[lang].astext.label("u")).where(
                Definition.id == definition_id
            )
        )
    ).first()
    if cached and cached.u:
        return {"cached": True, "url": cached.u}
    job = Job(
        type="tts_render",
        status="queued",
        payload={"definition_id": definition_id, "lang": lang},
        created_by_user_id=user.id,
    )
    session.add(job)
    await session.flush()
    await session.commit()
    return {"cached": False, "job_id": str(job.id)}
