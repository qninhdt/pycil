"""Public deck browse + clone endpoints.

`GET /public/decks` lists public decks paginated.
`GET /public/decks/{id}` returns a read-only snapshot (no auth).
`POST /public/decks/{id}/clone` deep-clones into the cloner's tree.

Rate limiting deferred to v0.3 — Caddy + slowapi middleware not yet
mounted in main.py.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from pycil_core.api.deps import SessionDep, UserDep
from pycil_core.services import clone_service


router = APIRouter(prefix="/public", tags=["public"])


@router.get("/decks")
async def list_public_decks(
    session: SessionDep,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
) -> dict:
    sql = """
    SELECT n.id, n.name, n.description, n.updated_at,
           (SELECT COUNT(*) FROM deck_definitions dd WHERE dd.deck_id = n.id) AS term_count,
           (SELECT COUNT(*) FROM deck_clones c WHERE c.source_deck_id = n.id) AS clone_count
      FROM nodes n
     WHERE n.type = 'DECK' AND n.visibility = 'PUBLIC'
    """
    params: dict = {"limit": limit + 1}
    if q:
        sql += " AND n.name % :q "
        params["q"] = q
    sql += " ORDER BY n.updated_at DESC, n.id DESC LIMIT :limit"

    rows = (await session.execute(text(sql), params)).all()
    next_cursor = None
    if len(rows) > limit:
        next_cursor = str(rows[limit].id)
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
async def get_public_deck(deck_id: UUID, session: SessionDep) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT id, name, description, updated_at
                  FROM nodes
                 WHERE id = :id AND type = 'DECK' AND visibility = 'PUBLIC'
                """
            ),
            {"id": deck_id},
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return {"new_deck_id": str(new_id)}
