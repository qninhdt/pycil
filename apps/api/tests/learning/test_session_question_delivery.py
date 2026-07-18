"""Phase-3 delivery boundaries: ready payloads never expose answer material."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from pycil.auth.models import User
from pycil.content.lexi_types import Question
from pycil.content.models import DeckSense
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import NodeType
from pycil.learning import session_store
from pycil.learning.models import UserSenseStats
from pycil.learning.question_delivery import find_question, ready_payload
from pycil.learning.session_queue import build_queue


class _LookupClient:
    def __init__(self, question: Question | None):
        self.question = question

    async def get_question_for_sense(self, sense_id: int, question_format: str):
        assert (sense_id, question_format) == (41, "definition_mcq")
        return self.question


@pytest.mark.asyncio
async def test_ready_question_is_selected_by_sense_and_sanitized():
    question = Question(
        id=7,
        word_id=3,
        sense_id=41,
        format="definition_mcq",
        answer_kind="choice",
        payload={"stem": "?", "options": ["a", "b"], "correct_index": 0},
    )
    selected = await find_question(_LookupClient(question), 41, "definition_mcq")
    assert selected is question
    assert ready_payload(selected, "definition_mcq") == {
        "question_id": 7,
        "sense_id": 41,
        "recommended_type": "definition_mcq",
        "format": "definition_mcq",
        "payload": {"stem": "?", "options": ["a", "b"]},
    }


@pytest.mark.parametrize(
    ("question_format", "payload", "expected"),
    [
        (
            "contextual_mcq",
            {"stem": "context", "options": ["a", "b"], "correct_index": 1},
            {"stem": "context", "options": ["a", "b"]},
        ),
        (
            "cloze",
            {"stem_with_blank": "A ___ B", "answer_norm": "word", "accepted_forms": ["words"]},
            {"stem_with_blank": "A ___ B"},
        ),
        (
            "use_in_sentence",
            {"prompt": "Write one", "target_norm": "word", "rubric": "hidden"},
            {"prompt": "Write one"},
        ),
    ],
)
def test_ready_payload_is_format_specific_and_never_serializes_answer_material(
    question_format, payload, expected
):
    question = Question(
        id=7,
        word_id=3,
        sense_id=41,
        format=question_format,
        answer_kind="choice",
        payload=payload,
    )
    delivered = ready_payload(question, question_format)
    assert delivered["format"] == question_format
    assert delivered["payload"] == expected


@pytest.mark.asyncio
async def test_only_one_concurrent_answer_claim_can_win(fake_redis):
    session_id = "claim-race"
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=uuid4(),
        node_id=uuid4(),
        scope_generation=0,
        queue=[session_store.QueuedSense(sense_id=41, mastery=0)],
    )
    await session_store.replace_issue(
        fake_redis,
        session_id,
        {"state": "ready", "question_id": 7, "sense_id": 41},
    )
    first = await session_store.claim_issue(fake_redis, session_id, 7)
    second = await session_store.claim_issue(fake_redis, session_id, 7)
    assert first is not None
    assert second is None
    assert await session_store.complete_issue(fake_redis, session_id, 7)
    state = await session_store.get(fake_redis, session_id)
    assert state is not None and state.cursor == 1 and state.issue is None


@pytest.mark.asyncio
async def test_expired_session_cannot_be_recreated_by_issue_mutation(fake_redis):
    session_id = "expired-session"
    await session_store.create(
        fake_redis,
        session_id,
        owner_id=uuid4(),
        node_id=uuid4(),
        scope_generation=0,
        queue=[],
    )
    await fake_redis.delete(f"session:{session_id}")
    assert not await session_store.replace_issue(
        fake_redis, session_id, {"state": "ready"}
    )
    assert await session_store.get(fake_redis, session_id) is None


@pytest.mark.asyncio
async def test_folder_and_reference_queue_is_distinct_and_excludes_buried(session):
    owner = User(email="queue-scope@example.com")
    session.add(owner)
    await session.commit()
    await session.refresh(owner)
    folder = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.FOLDER, name="root"
    )
    direct_deck = await hierarchy_service.create_node(
        session,
        owner.id,
        node_type=NodeType.DECK,
        name="direct",
        parent_node_id=folder.id,
    )
    target_deck = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="target"
    )
    await hierarchy_service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="target reference",
        parent_node_id=folder.id,
        target_node_id=target_deck.id,
    )
    session.add_all(
        [
            DeckSense(node_id=direct_deck.id, sense_id=1, position=0),
            DeckSense(node_id=direct_deck.id, sense_id=2, position=1),
            DeckSense(node_id=target_deck.id, sense_id=2, position=0),
            DeckSense(node_id=target_deck.id, sense_id=3, position=1),
            UserSenseStats(
                user_id=owner.id,
                sense_id=3,
                buried_until=datetime.now(UTC) + timedelta(days=1),
            ),
        ]
    )
    await session.commit()

    queue = await build_queue(session, owner.id, folder.id, datetime.now(UTC))
    assert {item.sense_id for item in queue} == {1, 2}
