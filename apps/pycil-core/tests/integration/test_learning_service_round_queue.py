"""Round queue replenishment on `learning_service._next_round_queue`.

Pinned:
- Drains incomplete-only definitions, in source order.
- All-completed → empty list (caller terminates session).
"""
from __future__ import annotations

from uuid import uuid4

from pycil_core.services.learning import session_flow as ls
from tests.factories import make_session_state


def test_next_round_queue_excludes_completed() -> None:
    state = make_session_state(
        session_id=str(uuid4()),
        user_id=uuid4(),
        deck_id=uuid4(),
        definition_ids=[10, 20, 30, 40, 50],
        completed=[20, 40],
    )
    assert ls._next_round_queue(state) == [10, 30, 50]


def test_next_round_queue_all_completed_returns_empty() -> None:
    state = make_session_state(
        session_id=str(uuid4()),
        user_id=uuid4(),
        deck_id=uuid4(),
        definition_ids=[1, 2, 3],
        completed=[1, 2, 3],
    )
    assert ls._next_round_queue(state) == []


def test_next_round_queue_preserves_definition_order() -> None:
    """Replenishment iterates `definition_ids` order, NOT the completed set."""
    state = make_session_state(
        session_id=str(uuid4()),
        user_id=uuid4(),
        deck_id=uuid4(),
        definition_ids=[7, 3, 9, 1, 5],
        completed=[3, 1],
    )
    assert ls._next_round_queue(state) == [7, 9, 5]
