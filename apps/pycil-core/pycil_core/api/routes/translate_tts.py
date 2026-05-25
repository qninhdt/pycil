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
from sqlalchemy import text

from pycil_core.api.deps import SessionDep, UserDep


router = APIRouter(prefix="/definitions", tags=["translate-tts"])

_SUPPORTED_LANGS = {"en", "vi", "ja", "ko", "es", "fr", "de"}


async def _assert_owner(session, *, definition_id: int, user_id) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT 1 FROM definitions d
                  JOIN deck_definitions dd ON dd.definition_id = d.id
                  JOIN nodes n ON n.id = dd.deck_id
                 WHERE d.id = :did AND n.author_id = :uid LIMIT 1
                """
            ),
            {"did": definition_id, "uid": user_id},
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
        await session.execute(
            text(
                "SELECT translation->:lang AS t FROM definitions WHERE id = :id"
            ),
            {"id": definition_id, "lang": lang},
        )
    ).first()
    if cached and cached.t is not None:
        return {"cached": True, "translation": cached.t}
    job = (
        await session.execute(
            text(
                "INSERT INTO jobs (type, status, payload) "
                "VALUES ('translate_definition', 'queued', "
                "CAST(:p AS jsonb)) RETURNING id"
            ),
            {"p": '{"definition_id":%d,"lang":"%s"}' % (definition_id, lang)},
        )
    ).one()
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
        await session.execute(
            text("SELECT tts_url->>:lang AS u FROM definitions WHERE id = :id"),
            {"id": definition_id, "lang": lang},
        )
    ).first()
    if cached and cached.u:
        return {"cached": True, "url": cached.u}
    job = (
        await session.execute(
            text(
                "INSERT INTO jobs (type, status, payload) "
                "VALUES ('tts_render', 'queued', CAST(:p AS jsonb)) RETURNING id"
            ),
            {"p": '{"definition_id":%d,"lang":"%s"}' % (definition_id, lang)},
        )
    ).one()
    await session.commit()
    return {"cached": False, "job_id": str(job.id)}
