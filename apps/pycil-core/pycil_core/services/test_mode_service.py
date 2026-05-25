"""Test (assessment) mode: pre-fetched, answer-stripped, no ELO writes.

`start_run` returns answer-stripped projection (prompt + MCQ choices only);
`expected_answer`/`alt_answers`/`correct_index` never leave BE until
user submits via `submit_answer`. View-source attack reveals nothing
useful.
"""
from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _to_client_payload(q_type: str, data: dict) -> dict:
    """Strip answer fields. Only `prompt` (or `stem`) + MCQ `options` leave BE."""
    if q_type == "MULTIPLE_CHOICE":
        return {"stem": data.get("stem"), "options": data.get("options", [])}
    return {"prompt": data.get("prompt")}


async def start_run(
    session: AsyncSession,
    *,
    user_id: UUID,
    deck_id: UUID,
    question_count: int,
    types: list[str],
) -> dict:
    """Select N questions from deck, INSERT run + items, return stripped payload."""
    owns = (
        await session.execute(
            text(
                """
                SELECT 1 FROM nodes
                 WHERE id = :did
                   AND type = 'DECK'
                   AND (author_id = :uid OR visibility = 'PUBLIC')
                """
            ),
            {"did": deck_id, "uid": user_id},
        )
    ).first()
    if owns is None:
        raise LookupError("deck_not_found_or_not_accessible")
    rows = (
        await session.execute(
            text(
                """
                SELECT q.id, q.type::text AS type, q.data
                  FROM questions q
                  JOIN deck_definitions dd ON dd.definition_id = q.definition_id
                 WHERE dd.deck_id = :did
                   AND q.type::text = ANY(:types)
                 ORDER BY random()
                 LIMIT :limit
                """
            ),
            {"did": deck_id, "types": types, "limit": question_count},
        )
    ).all()
    if not rows:
        raise LookupError("no_questions_available")

    run = (
        await session.execute(
            text(
                """
                INSERT INTO test_runs (user_id, deck_id, question_count)
                VALUES (:uid, :did, :n)
                RETURNING id
                """
            ),
            {"uid": user_id, "did": deck_id, "n": len(rows)},
        )
    ).one()
    run_id = run.id

    items = []
    for pos, r in enumerate(rows):
        item = (
            await session.execute(
                text(
                    """
                    INSERT INTO test_run_items (run_id, question_id, position)
                    VALUES (:rid, :qid, :pos)
                    RETURNING id
                    """
                ),
                {"rid": run_id, "qid": r.id, "pos": pos},
            )
        ).one()
        data = r.data
        if isinstance(data, str):
            data = json.loads(data)
        items.append({
            "item_id": str(item.id),
            "position": pos,
            "type": r.type,
            **_to_client_payload(r.type, data),
        })
    await session.commit()
    return {"run_id": str(run_id), "items": items}


async def submit_answer(
    session: AsyncSession,
    *,
    user_id: UUID,
    run_id: UUID,
    item_id: UUID,
    user_answer: str,
) -> dict:
    """Grade server-side. NO ELO writes (locked decision)."""
    from pycil_core.services import answer_grading_service

    row = (
        await session.execute(
            text(
                """
                SELECT i.id, i.position, q.type::text AS type, q.data,
                       r.user_id, r.completed_at, i.answered_at
                  FROM test_run_items i
                  JOIN test_runs r ON r.id = i.run_id
                  JOIN questions q ON q.id = i.question_id
                 WHERE i.id = :iid AND r.id = :rid AND r.user_id = :uid
                """
            ),
            {"iid": item_id, "rid": run_id, "uid": user_id},
        )
    ).first()
    if row is None or row.user_id != user_id:
        raise LookupError("item_not_found")
    if row.completed_at is not None:
        raise ValueError("run_completed")
    if row.answered_at is not None:
        raise ValueError("already_answered")

    data = row.data
    if isinstance(data, str):
        data = json.loads(data)

    if row.type == "MULTIPLE_CHOICE":
        try:
            chosen = int(user_answer)
        except (TypeError, ValueError):
            chosen = -1
        is_correct = chosen == int(data.get("correct_index", -1))
        reason = "exact"
    else:
        graded = answer_grading_service.grade(
            expected=data.get("expected_answer", ""),
            alts=data.get("alt_answers"),
            user_answer=user_answer,
        )
        is_correct = bool(graded["is_correct"])
        reason = str(graded["reason"])

    await session.execute(
        text(
            """
            UPDATE test_run_items
               SET user_answer = :ua, is_correct = :ic, answered_at = NOW()
             WHERE id = :iid
            """
        ),
        {"ua": user_answer, "ic": is_correct, "iid": item_id},
    )
    await session.commit()
    return {"is_correct": is_correct, "reason": reason}


async def complete_run(
    session: AsyncSession, *, user_id: UUID, run_id: UUID
) -> dict:
    """Finalize the run. Returns score breakdown."""
    summary = (
        await session.execute(
            text(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE is_correct) AS correct
                  FROM test_run_items
                 WHERE run_id = :rid
                """
            ),
            {"rid": run_id},
        )
    ).one()
    total = int(summary.total)
    correct = int(summary.correct)
    score_pct = (100.0 * correct / total) if total else 0.0

    await session.execute(
        text(
            """
            UPDATE test_runs
               SET completed_at = NOW(),
                   correct_count = :c,
                   score_pct = :p
             WHERE id = :rid AND user_id = :uid
            """
        ),
        {"c": correct, "p": score_pct, "rid": run_id, "uid": user_id},
    )
    await session.commit()
    return {"correct_count": correct, "total": total, "score_pct": score_pct}
