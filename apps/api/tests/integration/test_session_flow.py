"""Integration: full session flow against real Postgres + fakeredis + fake port.

start session → build queue → answer → mastery update + verdict persist-back.
LexiClient is faked at the port boundary (not the LLM); Postgres is real.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from pycil.auth.models import User
from pycil.content.lexi_types import Question, Score
from pycil.content.models import DeckSense
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import NodeType
from pycil.learning import service as learning_service
from pycil.learning.models import Response, ReviewLog, UserSenseStats
from pycil.learning.session_queue import build_queue

pytestmark = pytest.mark.asyncio


class IntegrationLexiClient:
    """Fake port serving one authoritative question + a canned correct verdict."""

    def __init__(self, question: Question):
        self._question = question

    async def get_question(self, question_id: int):
        return self._question if question_id == self._question.id else None

    async def grade(self, question, answer):
        return Score(correct=True, score=1.0, kind="rule")

    async def search(self, q):  # pragma: no cover
        return []

    async def generate(self, s):  # pragma: no cover
        ...

    async def get_senses(self, ids):  # pragma: no cover
        return []

    async def generate_questions(self, e, formats, n):  # pragma: no cover
        return []


async def _seed_deck_with_senses(session, owner, sense_ids):
    deck = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="integration deck"
    )
    for pos, sid in enumerate(sense_ids):
        session.add(DeckSense(node_id=deck.id, sense_id=sid, position=pos))
    await session.commit()
    return deck


async def test_full_session_flow(session):
    owner = User(email="flow@x.co")
    session.add(owner)
    await session.commit()
    await session.refresh(owner)

    deck = await _seed_deck_with_senses(session, owner, [101, 102, 103])
    q = Question(
        id=1, word_id=7, sense_id=101, format="definition_mcq",
        answer_kind="choice", payload={"prompt": "?", "options": ["a", "b"], "answer": 0},
    )
    client = IntegrationLexiClient(q)

    # 1. Queue is non-empty even though nothing is due (all new senses).
    queue = await build_queue(session, owner.id, deck.id, datetime.now(UTC))
    assert len(queue) == 3
    assert all(item.is_new for item in queue)

    # 2. Answer the first sense → stats + review_log + response all written.
    out = await learning_service.answer(
        session, client, owner.id, question_id=1, raw_answer="0",
        session_id="sess-1", now=datetime.now(UTC), seen_senses=set(),
    )
    assert out.is_correct and out.first_attempt

    stats = (await session.execute(
        select(UserSenseStats).where(UserSenseStats.sense_id == 101)
    )).scalars().first()
    assert stats is not None
    assert stats.review_count == 1
    assert stats.mastery > 0  # FSRS stability grew on a correct answer

    logs = (await session.execute(select(ReviewLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].sense_id == 101

    responses = (await session.execute(select(Response))).scalars().all()
    assert len(responses) == 1
    assert responses[0].is_correct is True
    assert responses[0].sense_id == 101

    # 3. Second attempt on the SAME sense in the same session → no S move.
    seen = {101}
    out2 = await learning_service.answer(
        session, client, owner.id, question_id=1, raw_answer="0",
        session_id="sess-1", now=datetime.now(UTC), seen_senses=seen,
    )
    assert not out2.first_attempt
    assert out2.stability_after == out.stability_after

    # Still only one review_log row (only first attempts log).
    assert len((await session.execute(select(ReviewLog))).scalars().all()) == 1
