"""Regression: single-column `select(Model.col)` must scalarize under `exec()`.

The raw-SQL→SQLModel conversion left `select` imported from `sqlalchemy` in
several services. SQLModel's `AsyncSession.exec()` only auto-scalarizes a
`sqlmodel.select`; a `sqlalchemy.select(Model.col)` returns a `Row`, not the
bare value. That silently breaks any call site that compares/consumes the
result as a scalar.

Pinned here:
- `claim_username`: re-saving your OWN username must NOT raise 409. With the
  bug, `existing_id` was a Row, `Row != user_id` was always True → false
  `username_taken`.
- `reverse_card.build_prompts`: distractor pool must be a list of meaning
  strings, not Row objects.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from pycil_core.services import reverse_card_service, social_service
from tests.factories import (
    make_deck,
    make_definition,
    make_term,
)


async def test_claim_username_idempotent_for_self(session, test_user) -> None:
    """Re-claiming the username you already hold must succeed (no 409)."""
    uid = test_user["id"]
    name = await social_service.claim_username(session, uid, "alice_01")
    await session.commit()
    assert name == "alice_01"

    # Second claim of the SAME name by the SAME user must be a no-op, not 409.
    again = await social_service.claim_username(session, uid, "alice_01")
    await session.commit()
    assert again == "alice_01"


async def test_claim_username_taken_by_other_raises(
    session, test_user, second_user
) -> None:
    """A name held by a DIFFERENT user must still raise 409 (guard intact)."""
    await social_service.claim_username(session, test_user["id"], "bob_99")
    await session.commit()

    with pytest.raises(HTTPException) as exc:
        await social_service.claim_username(session, second_user["id"], "bob_99")
    assert exc.value.status_code == 409


async def test_reverse_prompts_distractors_are_strings(
    session, test_user
) -> None:
    """Distractor pool must be meaning strings, not Row objects."""
    deck = await make_deck(session, author_id=test_user["id"])
    # build_prompts joins on deck_terms (term-level), so seed those rows.
    for i in range(5):
        tid = await make_term(session, value=f"rev-term-{i}")
        await make_definition(
            session, term_id=tid, canonical=f"meaning number {i}"
        )
        await session.execute(
            text(
                "INSERT INTO deck_terms (deck_id, term_id, position) "
                "VALUES (:d, :t, :p) ON CONFLICT DO NOTHING"
            ),
            {"d": deck["id"], "t": tid, "p": i},
        )
    await session.commit()

    prompts = await reverse_card_service.build_prompts(
        session, test_user["id"], deck["id"], limit=5, distractors_per=2
    )
    assert prompts
    for p in prompts:
        for d in p.distractors:
            assert isinstance(d, str), f"distractor is {type(d).__name__}, not str"
