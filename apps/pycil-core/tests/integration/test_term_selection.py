"""`term_selection.select_definition_ids` priority order.

Pinned: due > new > upcoming, with `definition_id ASC` deterministic tiebreak.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from pycil_core.learning import term_selection
from tests.factories import (
    attach_definition_to_deck,
    make_deck,
    make_definition,
    make_term,
)


async def test_due_terms_picked_before_new_and_upcoming(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])

    # Three definitions, three priority states.
    due_def = await make_definition(
        session, term_id=await make_term(session, value="due-1"),
    )
    new_def = await make_definition(
        session, term_id=await make_term(session, value="new-1"),
    )
    upcoming_def = await make_definition(
        session, term_id=await make_term(session, value="upcoming-1"),
    )
    for d in (due_def, new_def, upcoming_def):
        await attach_definition_to_deck(
            session, deck_id=deck["id"], definition_id=d
        )

    now = datetime.now(tz=UTC)

    async def _seed(def_id: int, nrd: datetime) -> None:
        await session.execute(
            text(
                """
                INSERT INTO user_term_stats (
                    user_id, definition_id, mastery_score, last_review_date,
                    next_review_date, interval_seconds, mastery_level
                )
                VALUES (:u, :d, 1000, :last, :nrd, 1800, 4)
                """
            ),
            {
                "u": test_user["id"],
                "d": def_id,
                "last": now - timedelta(hours=2),
                "nrd": nrd,
            },
        )
        await session.commit()

    await _seed(due_def, now - timedelta(minutes=10))         # due (past)
    await _seed(upcoming_def, now + timedelta(hours=24))       # upcoming
    # new_def: no `user_term_stats` row.

    picked = await term_selection.select_definition_ids(
        session, user_id=test_user["id"], deck_id=deck["id"], limit=10
    )
    # Order: due first, then new, then upcoming.
    assert picked == [due_def, new_def, upcoming_def]


async def test_select_respects_limit(session, test_user) -> None:
    deck = await make_deck(session, author_id=test_user["id"])
    ids = []
    for i in range(5):
        tid = await make_term(session, value=f"limit-{i}")
        did = await make_definition(session, term_id=tid)
        await attach_definition_to_deck(session, deck_id=deck["id"], definition_id=did)
        ids.append(did)

    picked = await term_selection.select_definition_ids(
        session, user_id=test_user["id"], deck_id=deck["id"], limit=3
    )
    assert len(picked) == 3
    assert set(picked).issubset(set(ids))
