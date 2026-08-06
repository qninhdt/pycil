"""End-to-end learning HTTP flow on the new level-based contract.

Drives /sessions -> /next -> /answers through the real app with a fake lexi reader
(the shipped contract), plus durable structural invariants (first-attempt claim,
pending raw-answer field, GradeResponse shape).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.auth.deps import current_user
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.content.infra.models import DeckSense
from pycil.db.session import get_session
from pycil.hierarchy.application import service as hierarchy_service
from pycil.hierarchy.infra.models import NodeType
from pycil.learning.infra.models import Response, UserSenseStats
from pycil.main import create_app
from pycil.ports.lexi_provider import get_lexi_client
from tests.learning.fakes import FakeLexiReader

pytestmark = pytest.mark.asyncio

_SENSE_ID = 101


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


class _FakeArqPool:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, *args):
        self.jobs.append(args)


@pytest_asyncio.fixture
async def learning_client(engine, monkeypatch):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        owner = await _user(session, "learn-owner@example.com")
        deck = await hierarchy_service.create_node(
            session, owner.id, node_type=NodeType.DECK, name="learning deck"
        )
        session.add(DeckSense(node_id=deck.id, sense_id=_SENSE_ID, position=0))
        await session.commit()

    reader = FakeLexiReader()
    # Warm supply for acquisition (level-1) checkpoints + retries.
    reader.add_supply(_SENSE_ID, 1, "definition_mcq", count=5)

    fake_pool = _FakeArqPool()

    async def _fake_arq_pool():
        return fake_pool

    # Both modules enqueue: session_flow for supply warm-up, answering for grading.
    monkeypatch.setattr("pycil.learning.application.session_flow.get_arq_pool", _fake_arq_pool)
    monkeypatch.setattr("pycil.learning.application.answering.get_arq_pool", _fake_arq_pool)

    async def override_session():
        async with factory() as s:
            yield s

    async def override_user() -> CurrentUser:
        return CurrentUser(id=owner.id, email=owner.email)

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[current_user] = override_user
    app.dependency_overrides[get_lexi_client] = lambda: reader
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, owner, deck, reader


async def _next_ready(client, session_id, limit=6):
    """Poll /next, skipping break/preparing, until a ready item or terminal state."""
    last = None
    for _ in range(limit):
        res = await client.get(f"/v1/sessions/{session_id}/next")
        assert res.status_code == 200
        last = res.json()
        if last["state"] in ("ready", "exhausted", "waiting"):
            return last
    return last


async def test_new_sense_first_delivered_as_exposure(learning_client):
    client, *_ = learning_client
    started = await client.post("/v1/sessions", json={"nodeId": str(_deck_id(learning_client))})
    assert started.status_code == 200
    session_id = started.json()["sessionId"]

    first = await _next_ready(client, session_id)
    assert first["state"] == "ready"
    assert first["renderFormat"] == "flashcard"
    assert first["interactionMode"] == "exposure"
    # Presentation only — no grading keys leak.
    assert "correct_index" not in first["payload"]


async def test_acquisition_checkpoint_graded_in_request(learning_client):
    client, factory, owner, deck, reader = learning_client
    started = await client.post("/v1/sessions", json={"nodeId": str(deck.id)})
    session_id = started.json()["sessionId"]

    # Exposure first, then poll to the first assessment checkpoint (later round).
    exposure = await _next_ready(client, session_id)
    assert exposure["renderFormat"] == "flashcard"
    checkpoint = await _next_ready(client, session_id)
    assert checkpoint["state"] == "ready"
    assert checkpoint["renderFormat"] == "single_choice"
    assert checkpoint["interactionMode"] == "assessment"
    qid = checkpoint["questionId"]

    # Correct rule-type answer grades in-request (D2).
    answered = await client.post(
        "/v1/answers",
        json={"sessionId": session_id, "questionId": qid, "answer": "a"},
    )
    assert answered.status_code == 200
    body = answered.json()
    assert body["gradeStatus"] == "graded"
    assert body["renderFormat"] == "single_choice"
    assert body["isCorrect"] is True
    assert "reveal" in body
    assert body["reveal"]["correct_index"] == 0


async def test_answer_rejects_unissued_question_without_state_write(learning_client):
    client, factory, owner, deck, reader = learning_client
    started = await client.post("/v1/sessions", json={"nodeId": str(deck.id)})
    session_id = started.json()["sessionId"]

    res = await client.post(
        "/v1/answers",
        json={"sessionId": session_id, "questionId": 999999, "answer": "a"},
    )
    assert res.status_code == 409
    async with factory() as session:
        written = (
            await session.execute(
                select(UserSenseStats).where(UserSenseStats.user_id == owner.id)
            )
        ).scalars().all()
    assert written == []


def _deck_id(learning_client):
    return learning_client[3].id


async def test_first_attempt_has_a_database_uniqueness_claim():
    from pycil.learning.infra import models

    unique_sets = {
        tuple(column.name for column in constraint.columns)
        if hasattr(constraint, "columns")
        else ()
        for constraint in models.SessionSenseAttempt.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("user_id", "session_id", "sense_id") in unique_sets


async def test_pending_response_has_dedicated_raw_answer_field():
    assert "raw_answer" in Response.model_fields
    assert "requested_level" in Response.model_fields
    assert "served_level" in Response.model_fields
    assert "render_format" in Response.model_fields
    assert "reveal" in Response.model_fields


async def test_answer_contract_exposes_grade_fields():
    schemas = create_app().openapi()["components"]["schemas"]
    props = schemas["GradeResponse"]["properties"]
    assert {"responseId", "gradeStatus", "renderFormat", "reveal", "taskId"} <= props.keys()
