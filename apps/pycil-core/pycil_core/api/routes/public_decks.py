"""Public deck browse + clone endpoints.

`GET /public/decks` lists public decks paginated.
`GET /public/decks/{id}` returns a read-only snapshot (no auth).
`POST /public/decks/{id}/clone` deep-clones into the cloner's tree.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from shared.db import Node
from shared.db.enums import NodeType, Visibility
from sqlalchemy import select, text

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.middleware.rate_limit import client_ip, enforce
from pycil_core.services import clone_service

router = APIRouter(prefix="/public", tags=["public"])


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
    ts_str, _, id_str = raw.partition("|")
    return datetime.fromisoformat(ts_str), UUID(id_str)


def _encode_cursor(ts: datetime, deck_id: UUID) -> str:
    raw = f"{ts.isoformat()}|{deck_id}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii")


@router.get("/decks")
async def list_public_decks(
    request: Request,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
) -> dict:
    await enforce(client_ip(request), "public_list")
    sql = """
    SELECT n.id, n.name, n.description, n.updated_at,
           (SELECT COUNT(*) FROM deck_definitions dd WHERE dd.deck_id = n.id) AS term_count,
           (SELECT COUNT(*) FROM deck_clones c WHERE c.source_deck_id = n.id) AS clone_count
      FROM nodes n
     WHERE n.type = 'DECK' AND n.visibility = 'PUBLIC'
    """
    params: dict = {"limit": limit + 1}
    if cursor:
        try:
            cur_ts, cur_id = _decode_cursor(cursor)
        except (ValueError, TypeError, binascii.Error) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_cursor") from exc
        sql += " AND (n.updated_at, n.id) < (:cur_ts, :cur_id) "
        params["cur_ts"] = cur_ts
        params["cur_id"] = cur_id
    if q:
        sql += " AND n.name % :q "
        params["q"] = q
    sql += " ORDER BY n.updated_at DESC, n.id DESC LIMIT :limit"

    rows = (await session.execute(text(sql), params)).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.updated_at, last.id)
        rows = rows[:limit]
    return {
        "decks": [
            {
                "id": str(r.id),
                "name": r.name,
                "description": r.description,
                "term_count": int(r.term_count),
                "clone_count": int(r.clone_count),
            }
            for r in rows
        ],
        "next_cursor": next_cursor,
    }


@router.get("/decks/{deck_id}")
async def get_public_deck(deck_id: UUID, request: Request, session: SessionDep) -> dict:
    await enforce(client_ip(request), "public_get")
    row = (
        await session.exec(
            select(
                Node.id,
                Node.name,
                Node.description,
                Node.updated_at,
            ).where(
                Node.id == deck_id,
                Node.type == NodeType.DECK,
                Node.visibility == Visibility.PUBLIC,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deck_not_found")
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("/decks/{deck_id}/clone")
async def clone_public_deck(
    deck_id: UUID, user: UserDep, session: SessionDep
) -> dict:
    try:
        new_id = await clone_service.deep_clone(
            session, user_id=user.id, source_deck_id=deck_id
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"new_deck_id": str(new_id)}
