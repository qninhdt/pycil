"""Known session, persistence, grading, and realtime contract gaps."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from lexi_ai.read_models import Question, Score
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.auth.deps import current_user
from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.content.deps import get_lexi_client
from pycil.content.models import DeckSense
from pycil.db.session import get_session
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import NodeType
from pycil.learning import service
from pycil.learning.models import Response, ReviewLog, UserSenseStats
from pycil.main import create_app

pytestmark = pytest.mark.asyncio


class _QuestionClient:
    def __init__(self, sense_id: int = 999):
        self.sense_id = sense_id

    async def get_question(self, question_id: int):
        return Question(
            id=question_id,
            word_id=1,
            sense_id=self.sense_id,
            format="definition_mcq",
            answer_kind="choice",
            payload={"prompt": "?", "options": ["a", "b"], "answer": 0},
        )

    async def get_question_for_sense(self, sense_id: int, question_format: str):
        return Question(
            id=13,
            word_id=1,
            sense_id=sense_id,
            format=question_format,
            answer_kind="choice",
            payload={"prompt": "?", "options": ["a", "b"], "answer": 0},
        )

    async def grade(self, question, answer):
        return Score(correct=True, score=1.0, kind="rule")


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def learning_client(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        owner = await _user(session, "session-contract-owner@example.com")
        deck = await hierarchy_service.create_node(
            session, owner.id, node_type=NodeType.DECK, name="contract deck"
        )
        session.add(DeckSense(node_id=deck.id, sense_id=101, position=0))
        await session.commit()

    async def override_session():
        async with factory() as session:
            yield session

    async def override_user() -> CurrentUser:
        return CurrentUser(id=owner.id, email=owner.email, role=owner.role)

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[current_user] = override_user
    app.dependency_overrides[get_lexi_client] = lambda: _QuestionClient()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory, owner, deck


async def test_started_session_serves_a_retry_safe_queue_item(learning_client):
    client, _, _, deck = learning_client
    started = await client.post("/sessions", json={"nodeId": str(deck.id)})
    assert started.status_code == 200
    session_id = started.json()["sessionId"]

    first = await client.get(f"/sessions/{session_id}/next")
    second = await client.get(f"/sessions/{session_id}/next")

    assert first.status_code == 200
    assert first.json()["state"] == "ready"
    assert "answer" not in first.json()["payload"]
    assert second.json() == first.json()


async def test_api_rejects_out_of_queue_answer_without_state_write(
    learning_client, monkeypatch
):
    from pycil.realtime import client as realtime_client

    async def no_publish(*args, **kwargs):
        return None

    monkeypatch.setattr(realtime_client, "publish", no_publish)
    client, factory, owner, deck = learning_client
    started = await client.post("/sessions", json={"nodeId": str(deck.id)})
    response = await client.post(
        "/answers",
        json={
            "sessionId": started.json()["sessionId"],
            "questionId": 77,
            "answer": "0",
        },
    )
    async with factory() as session:
        written = (
            await session.execute(
                select(UserSenseStats).where(UserSenseStats.user_id == owner.id)
            )
        ).scalars().all()

    assert response.status_code == 409
    assert written == []


async def test_first_attempt_has_a_database_uniqueness_claim():
    from pycil.learning import models

    assert hasattr(models, "SessionSenseAttempt")
    attempt = models.SessionSenseAttempt
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in attempt.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("user_id", "session_id", "sense_id") in unique_column_sets


async def test_review_log_stability_before_matches_previous_state(session):
    owner = await _user(session, "history-owner@example.com")
    client = _QuestionClient(sense_id=55)
    first_at = datetime.now(UTC) - timedelta(days=2)
    await service.answer(
        session, client, owner.id, 1, "0", "first", first_at, set()
    )
    prior = await session.get(UserSenseStats, (owner.id, 55))
    prior_stability = prior.stability
    await service.answer(
        session, client, owner.id, 1, "0", "second", datetime.now(UTC), set()
    )
    logs = (
        await session.execute(select(ReviewLog).order_by(ReviewLog.reviewed_at))
    ).scalars().all()

    assert logs[-1].stability_before == pytest.approx(prior_stability)


async def test_pending_response_has_dedicated_raw_answer_field():
    assert "raw_answer" in Response.model_fields


async def test_answer_contract_exposes_response_id_and_grade_status():
    operation = create_app().openapi()["paths"]["/answers"]["post"]
    schema_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    schema_name = schema_ref.rsplit("/", 1)[-1]
    properties = create_app().openapi()["components"]["schemas"][schema_name]["properties"]

    assert {"responseId", "gradeStatus"} <= properties.keys()
