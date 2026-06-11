"""Test data factories.

Pure SQL inserts via raw `text()` so we stay decoupled from SQLModel — the
schema is the source of truth (alembic migrations) and tests pin behavior
on top of that, not the model layer.
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def make_user(
    session: AsyncSession, *, email: str | None = None, name: str = "Tester"
) -> dict:
    email = email or f"u-{uuid4().hex[:8]}@example.test"
    row = (
        await session.execute(
            text(
                "INSERT INTO users (email, name) VALUES (:e, :n) RETURNING id"
            ),
            {"e": email, "n": name},
        )
    ).one()
    await session.commit()
    return {"id": row.id, "email": email, "name": name}


async def make_deck(
    session: AsyncSession,
    *,
    author_id: UUID,
    name: str = "Test Deck",
    visibility: str = "PRIVATE",
    parent_node_id: UUID | None = None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO nodes (author_id, type, parent_node_id, name, visibility)
                VALUES (:aid, 'DECK', :pid, :n, CAST(:v AS visibility))
                RETURNING id
                """
            ),
            {"aid": author_id, "pid": parent_node_id, "n": name, "v": visibility},
        )
    ).one()
    await session.commit()
    return {"id": row.id, "name": name, "visibility": visibility}


async def make_term(
    session: AsyncSession, *, value: str, term_type: str = "SINGLE_WORD"
) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO terms (value, type) VALUES (:v, CAST(:t AS term_type))
                ON CONFLICT (value) DO UPDATE SET value = EXCLUDED.value
                RETURNING id
                """
            ),
            {"v": value, "t": term_type},
        )
    ).one()
    await session.commit()
    return row.id


async def make_definition(
    session: AsyncSession,
    *,
    term_id: int,
    cefr: str = "B1",
    pos: str = "NOUN",
    canonical: str = "a test definition",
) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO definitions (
                    term_id, cefr_level, part_of_speech,
                    synonyms, antonyms, notes, canonical_meaning
                )
                VALUES (
                    :tid, CAST(:cefr AS cefr_level), CAST(:pos AS part_of_speech),
                    :syn, :ant, :notes, :canonical
                )
                ON CONFLICT (term_id, sense_index) DO UPDATE
                  SET canonical_meaning = EXCLUDED.canonical_meaning
                RETURNING id
                """
            ),
            {
                "tid": term_id,
                "cefr": cefr,
                "pos": pos,
                "syn": [],
                "ant": [],
                "notes": [],
                "canonical": canonical,
            },
        )
    ).one()
    await session.commit()
    return row.id


async def attach_definition_to_deck(
    session: AsyncSession, *, deck_id: UUID, definition_id: int, position: int = 0
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO deck_definitions (deck_id, definition_id, position)
            VALUES (:did, :defid, :pos)
            ON CONFLICT (deck_id, definition_id) DO NOTHING
            """
        ),
        {"did": deck_id, "defid": definition_id, "pos": position},
    )
    await session.commit()


async def make_mcq_question(
    session: AsyncSession,
    *,
    definition_id: int,
    stem: str = "What does it mean?",
    options: list[str] | None = None,
    correct_index: int = 0,
    explanation: str = "Because reasons.",
) -> dict:
    options = options or ["right", "wrong-1", "wrong-2", "wrong-3"]
    data = {
        "stem": stem,
        "options": options,
        "correct_index": correct_index,
        "explanation": explanation,
        "distractor_rationale": ["d1", "d2", "d3"],
    }
    row = (
        await session.execute(
            text(
                """
                INSERT INTO questions (definition_id, type, data)
                VALUES (:did, CAST('MULTIPLE_CHOICE' AS question_type), CAST(:data AS jsonb))
                RETURNING id, type::text AS type, data
                """
            ),
            {"did": definition_id, "data": json.dumps(data)},
        )
    ).one()
    await session.commit()
    return {"id": row.id, "type": row.type, "data": data}


async def make_write_question(
    session: AsyncSession,
    *,
    definition_id: int,
    prompt: str = "Translate the term.",
    expected_answer: str = "answer",
    alt_answers: list[str] | None = None,
) -> dict:
    data = {
        "prompt": prompt,
        "expected_answer": expected_answer,
        "alt_answers": alt_answers or [],
        "explanation": "",
    }
    row = (
        await session.execute(
            text(
                """
                INSERT INTO questions (definition_id, type, data)
                VALUES (:did, CAST('WRITE' AS question_type), CAST(:data AS jsonb))
                RETURNING id
                """
            ),
            {"did": definition_id, "data": json.dumps(data)},
        )
    ).one()
    await session.commit()
    return {"id": row.id, "data": data}


async def seed_user_term_stats(
    session: AsyncSession,
    *,
    user_id: UUID,
    definition_id: int,
    mastery_score: int = 1000,
    interval_seconds: int = 1800,
    last_review_offset_seconds: int = 3600,
) -> None:
    last = datetime.now(tz=UTC) - timedelta(seconds=last_review_offset_seconds)
    nrd = last + timedelta(seconds=interval_seconds)
    await session.execute(
        text(
            """
            INSERT INTO user_term_stats (
                user_id, definition_id, mastery_score, last_review_date,
                next_review_date, interval_seconds, mastery_level
            )
            VALUES (:uid, :did, :elo, :last, :nrd, :iv, 4)
            ON CONFLICT (user_id, definition_id) DO UPDATE
              SET mastery_score = EXCLUDED.mastery_score,
                  last_review_date = EXCLUDED.last_review_date,
                  next_review_date = EXCLUDED.next_review_date,
                  interval_seconds = EXCLUDED.interval_seconds
            """
        ),
        {
            "uid": user_id,
            "did": definition_id,
            "elo": mastery_score,
            "last": last,
            "nrd": nrd,
            "iv": interval_seconds,
        },
    )
    await session.commit()


def make_session_state(
    *,
    session_id: str,
    user_id: UUID,
    deck_id: UUID,
    definition_ids: list[int],
    completed: list[int] | None = None,
    correct_firsts: dict[int, int] | None = None,
    current_question_id: str | None = None,
    current_definition_id: int | None = None,
    round_index: int = 0,
) -> dict[str, Any]:
    """Hand-roll a learning_service state matching `_initial_state` shape."""
    completed_set = set(completed or [])
    cf = correct_firsts or {}
    return {
        "id": session_id,
        "user_id": str(user_id),
        "deck_id": str(deck_id),
        "definition_ids": definition_ids,
        "term_tracking": {
            str(d): {
                "correct_firsts": int(cf.get(d, 0)),
                "is_first_attempt": True,
                "elo_at_start": 1000,
                "completed": d in completed_set,
            }
            for d in definition_ids
        },
        "round_index": round_index,
        "round_queue": [d for d in definition_ids if d not in completed_set],
        "current_question_id": current_question_id,
        "current_definition_id": current_definition_id,
        "started_at": time.time(),
    }
