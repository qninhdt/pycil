"""Search across decks, folders, terms, definitions via pg_trgm GIN.

Single endpoint `GET /search?q=` returns grouped results. Trigram threshold
is set per-connection via SET LOCAL to avoid bleed across pooled sessions.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def search(
    session: AsyncSession,
    *,
    user_id: UUID,
    q: str,
    limit: int = 10,
) -> dict[str, list[dict]]:
    """Trigram search scoped to user's owned content. Returns grouped results."""
    if not q or len(q.strip()) < 2:
        return {"nodes": [], "terms": [], "definitions": []}

    await session.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.2"))

    nodes = (
        await session.execute(
            text(
                """
                SELECT id, name, type::text AS type, parent_node_id,
                       similarity(name, :q) AS score
                  FROM nodes
                 WHERE author_id = :uid
                   AND name % :q
                 ORDER BY score DESC, name
                 LIMIT :limit
                """
            ),
            {"uid": user_id, "q": q, "limit": limit},
        )
    ).all()

    terms = (
        await session.execute(
            text(
                """
                SELECT DISTINCT t.id, t.value, similarity(t.value, :q) AS score
                  FROM terms t
                  JOIN definitions d ON d.term_id = t.id
                  JOIN deck_definitions dd ON dd.definition_id = d.id
                  JOIN nodes n ON n.id = dd.deck_id
                 WHERE n.author_id = :uid
                   AND t.value % :q
                 ORDER BY score DESC, t.value
                 LIMIT :limit
                """
            ),
            {"uid": user_id, "q": q, "limit": limit},
        )
    ).all()

    defs = (
        await session.execute(
            text(
                """
                SELECT d.id, d.canonical_meaning, t.value AS term_value,
                       similarity(d.canonical_meaning, :q) AS score
                  FROM definitions d
                  JOIN terms t ON t.id = d.term_id
                  JOIN deck_definitions dd ON dd.definition_id = d.id
                  JOIN nodes n ON n.id = dd.deck_id
                 WHERE n.author_id = :uid
                   AND d.canonical_meaning IS NOT NULL
                   AND d.canonical_meaning % :q
                 ORDER BY score DESC
                 LIMIT :limit
                """
            ),
            {"uid": user_id, "q": q, "limit": limit},
        )
    ).all()

    return {
        "nodes": [
            {
                "id": str(r.id),
                "name": r.name,
                "type": r.type,
                "parent_node_id": str(r.parent_node_id) if r.parent_node_id else None,
                "score": float(r.score),
            }
            for r in nodes
        ],
        "terms": [
            {"id": int(r.id), "value": r.value, "score": float(r.score)}
            for r in terms
        ],
        "definitions": [
            {
                "id": int(r.id),
                "term_value": r.term_value,
                "canonical_meaning": r.canonical_meaning,
                "score": float(r.score),
            }
            for r in defs
        ],
    }
