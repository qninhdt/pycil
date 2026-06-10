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
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from pycil_core.services import social_service


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

