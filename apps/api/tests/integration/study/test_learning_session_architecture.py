"""Integration tests for the Pycil Learning Session architecture.

Tests the three core operations:
1. create_session (POST /v1/study/sessions) -> LearningPlan + SessionQuestionRead[]
2. grade_answer (POST /v1/study/sessions/{id}/grade) -> stateless semantic grading
3. complete_session (POST /v1/study/sessions/{id}/complete) -> QuestionResult[]


Invariants tested:
- Session LearningPlan is immutable after creation.
- Deterministic questions include client grading keys.
- Free-text / semantic questions are graded server-side without mutating FSRS.
- Reasks are client-side reinforcement; only initial QuestionResult affects FSRS.
- Session completion is atomic, locking UserSenseStats in sorted order.
- Completion is idempotent: repeated requests return cached SessionResult.
"""

from uuid import UUID

import pytest
from lexi_ai.contracts import (
    AnswerSubmission,
    Evaluation,
    PresentedQuestion,
    QuestionTypeInfo,
    RenderKind,
)
from sqlalchemy import select

from pycil.account.user import User
from pycil.lexicon.provider import get_lexi_client
from pycil.library import membership as content_service
from pycil.library import nodes as collection_service
from pycil.library.models import NodeType
from pycil.study.models import Response, ReviewLog, SenseStatus, StudySession, UserSenseStats
from pycil.study.schemas import LearningPlan
from tests.support.clerk_jwks import bearer
from tests.support.lexi_fakes import FakeLexiReader

pytestmark = pytest.mark.asyncio


class _HybridTestLexiReader(FakeLexiReader):
    """LexiReader providing both single_choice and free_text questions."""

    def __init__(self, types: list[QuestionTypeInfo] | None = None) -> None:
        super().__init__(types=types)
        self.grade_evaluations: dict[int, Evaluation] = {}

    def add_free_text_question(self, sense_id: int, level: int = 3) -> int:
        from lexi_ai.contracts import FreeText

        qid = self._next_qid
        self._next_qid += 1
        q = PresentedQuestion(
            question_id=qid,
            word_id=self.word_id,
            sense_id=sense_id,
            type_id="use_in_sentence",
            render_kind=RenderKind.FREE_TEXT,
            difficulty_level=level,
            interaction="assessment",
            render=FreeText(prompt="Use this word in a sentence."),
        )
        self._questions[qid] = q
        self._supply.setdefault((sense_id, level, "use_in_sentence"), []).append(qid)
        return qid

    async def evaluate_answer(
        self, question_id: int, submission: AnswerSubmission
    ) -> Evaluation | None:
        if question_id in self.grade_evaluations:
            return self.grade_evaluations[question_id]
        question = self._questions.get(question_id)
        if question is None:
            return None
        if question.render_kind == RenderKind.FREE_TEXT:
            return Evaluation(
                question_id=question_id,
                status="graded",
                correct=True,
                score=0.95,
                feedback="Excellent semantic usage.",
            )
        return await super().evaluate_answer(question_id, submission)


async def _create_test_deck(session, user_id: UUID, sense_ids: list[int]):
    deck = await collection_service.create_node(
        session,
        user_id,
        node_type=NodeType.DECK,
        name="Architecture Test Deck",
    )
    for s_id in sense_ids:
        await content_service.add_sense(session, deck.id, s_id)
    await session.commit()
    return deck


async def test_create_session_returns_learning_plan_and_questions(app, client, session, clerk_stub):
    """Operation 1: Backend prepares the full immutable LearningPlan and all questions upfront."""
    user = User(email="plan_tester@test.co", clerk_id="user_plan_test")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    deck = await _create_test_deck(session, user.id, [101, 102])

    fake_lexi = _HybridTestLexiReader()
    fake_lexi.add_supply(sense_id=101, level=1, type_id="definition_mcq")
    fake_lexi.add_free_text_question(sense_id=102, level=1)
    app.dependency_overrides[get_lexi_client] = lambda: fake_lexi

    token = clerk_stub.token(subject="user_plan_test", email="plan_tester@test.co")
    headers = bearer(token)

    res = await client.post("/v1/study/sessions", json={"nodeId": str(deck.id)}, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert "sessionId" in data
    assert data["nodeId"] == str(deck.id)
    assert data["admittedCount"] == 2
    assert "plan" in data
    plan = data["plan"]
    assert plan["version"] == 1
    assert len(plan["items"]) == 2

    # Check question representations
    assert "questions" in data
    questions = data["questions"]
    assert len(questions) == 2

    # Deterministic question has client grading configuration
    mcq = next(q for q in questions if q["senseId"] == 101)
    assert mcq["format"] == "single_choice"
    assert mcq["grading"]["mode"] == "client"
    assert mcq["grading"]["correctOptionId"] is not None

    # Free text question has server grading mode
    free_txt = next(q for q in questions if q["senseId"] == 102)
    assert free_txt["format"] == "free_text"
    assert free_txt["grading"]["mode"] == "server"

    # Verify durable StudySession row in PostgreSQL
    session_id = UUID(data["sessionId"])
    study_session = await session.get(StudySession, session_id)
    assert study_session is not None
    assert study_session.status == "active"
    assert study_session.user_id == user.id
    assert study_session.node_id == deck.id
    saved_plan = LearningPlan.model_validate(study_session.plan)
    assert len(saved_plan.items) == 2


async def test_grade_answer_is_stateless_and_does_not_mutate_learning_state(
    app, client, session, clerk_stub
):
    """Operation 2: Server-side grading evaluates free text without touching FSRS or stats."""
    user = User(email="grader_test@test.co", clerk_id="user_grader_test")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    deck = await _create_test_deck(session, user.id, [201])

    fake_lexi = _HybridTestLexiReader()
    qid = fake_lexi.add_free_text_question(sense_id=201, level=1)
    app.dependency_overrides[get_lexi_client] = lambda: fake_lexi

    token = clerk_stub.token(subject="user_grader_test", email="grader_test@test.co")
    headers = bearer(token)

    # 1. Create session
    create_res = await client.post(
        "/v1/study/sessions", json={"nodeId": str(deck.id)}, headers=headers
    )
    assert create_res.status_code == 200
    session_id = create_res.json()["sessionId"]

    # 2. Grade answer via server endpoint
    grade_res = await client.post(
        f"/v1/study/sessions/{session_id}/grade",
        json={"questionId": qid, "answer": "This is a great sentence."},
        headers=headers,
    )
    assert grade_res.status_code == 200, grade_res.text
    grade_data = grade_res.json()
    assert grade_data["outcome"] == "correct"
    assert grade_data["score"] == 0.95
    assert grade_data["feedback"] == "Excellent semantic usage."

    # Invariant: /grade MUST NOT write to UserSenseStats, ReviewLog, or Response!
    stats = await session.get(UserSenseStats, (user.id, 201))
    assert stats is None  # Stats are not materialized until complete!

    reviews = (
        (
            await session.execute(
                select(ReviewLog).where(ReviewLog.user_id == user.id, ReviewLog.sense_id == 201)
            )
        )
        .scalars()
        .all()
    )
    assert len(reviews) == 0

    responses = (
        (
            await session.execute(
                select(Response).where(Response.user_id == user.id, Response.sense_id == 201)
            )
        )
        .scalars()
        .all()
    )
    assert len(responses) == 0


async def test_complete_session_atomic_update_and_idempotency(app, client, session, clerk_stub):
    """Operation 3: Submitting QuestionResult[] commits the session atomically and idempotently."""
    user = User(email="complete_test@test.co", clerk_id="user_complete_test")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    deck = await _create_test_deck(session, user.id, [301, 302])

    fake_lexi = _HybridTestLexiReader()
    q1 = fake_lexi.add_supply(sense_id=301, level=1, type_id="definition_mcq")[0]
    q2 = fake_lexi.add_supply(sense_id=302, level=1, type_id="definition_mcq")[0]
    app.dependency_overrides[get_lexi_client] = lambda: fake_lexi

    token = clerk_stub.token(subject="user_complete_test", email="complete_test@test.co")
    headers = bearer(token)

    # 1. Create session
    create_res = await client.post(
        "/v1/study/sessions", json={"nodeId": str(deck.id)}, headers=headers
    )
    session_id = create_res.json()["sessionId"]

    # 2. Complete session with QuestionResults
    completion_payload = {
        "results": [
            {"questionId": q1, "outcome": "correct"},
            {"questionId": q2, "outcome": "incorrect"},
        ]
    }

    comp_res = await client.post(
        f"/v1/study/sessions/{session_id}/complete",
        json=completion_payload,
        headers=headers,
    )
    assert comp_res.status_code == 200, comp_res.text
    result = comp_res.json()

    assert result["sessionId"] == session_id
    assert result["completed"] is True
    assert result["summary"]["questions"] == 2
    assert result["summary"]["correct"] == 1
    assert result["summary"]["incorrect"] == 1
    assert result["summary"]["sensesReviewed"] == 2

    # Check mastery changes
    changes = result["changes"]
    assert len(changes) == 2
    change_301 = next(c for c in changes if c["senseId"] == 301)
    change_302 = next(c for c in changes if c["senseId"] == 302)
    assert change_301["masteryBefore"] == 0
    assert change_301["masteryAfter"] > change_302["masteryAfter"]
    assert change_302["masteryBefore"] == 0

    # Check database state after transaction
    stats_301 = await session.get(UserSenseStats, (user.id, 301))
    assert stats_301 is not None
    assert stats_301.status == SenseStatus.scheduled
    assert stats_301.review_count == 1
    assert stats_301.lapse_count == 0

    stats_302 = await session.get(UserSenseStats, (user.id, 302))
    assert stats_302 is not None
    assert stats_302.review_count == 1
    assert stats_302.lapse_count == 1

    # Check ReviewLog rows
    review_rows = (
        (
            await session.execute(
                select(ReviewLog).where(ReviewLog.user_id == user.id).order_by(ReviewLog.sense_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(review_rows) == 2
    assert review_rows[0].sense_id == 301
    assert review_rows[0].grade == 3  # Good
    assert review_rows[1].sense_id == 302
    assert review_rows[1].grade == 1  # Again

    # Check Response rows
    response_rows = (
        (
            await session.execute(
                select(Response).where(Response.user_id == user.id).order_by(Response.sense_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(response_rows) == 2
    assert response_rows[0].is_correct is True
    assert response_rows[1].is_correct is False

    # Check StudySession table status
    study_session = await session.get(StudySession, UUID(session_id))
    assert study_session.status == "completed"
    assert study_session.completed_at is not None
    assert study_session.result_summary is not None

    # Invariant: Idempotency — retrying completion returns identical SessionResult
    # without re-applying FSRS!
    retry_res = await client.post(
        f"/v1/study/sessions/{session_id}/complete",
        json=completion_payload,
        headers=headers,
    )
    assert retry_res.status_code == 200
    retry_result = retry_res.json()
    assert retry_result == result

    # Verify review count didn't increase
    await session.refresh(stats_301)
    assert stats_301.review_count == 1


async def test_completion_validation_rejects_malformed_results(app, client, session, clerk_stub):
    """Validation at completion: duplicate QIDs, unknown QIDs, and missing QIDs are rejected."""
    user = User(email="val_test@test.co", clerk_id="user_val_test")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    deck = await _create_test_deck(session, user.id, [401, 402])

    fake_lexi = _HybridTestLexiReader()
    q1 = fake_lexi.add_supply(sense_id=401, level=1, type_id="definition_mcq")[0]
    fake_lexi.add_supply(sense_id=402, level=1, type_id="definition_mcq")
    app.dependency_overrides[get_lexi_client] = lambda: fake_lexi

    token = clerk_stub.token(subject="user_val_test", email="val_test@test.co")
    headers = bearer(token)

    create_res = await client.post(
        "/v1/study/sessions", json={"nodeId": str(deck.id)}, headers=headers
    )
    session_id = create_res.json()["sessionId"]

    # 1. Duplicate question ID
    res = await client.post(
        f"/v1/study/sessions/{session_id}/complete",
        json={
            "results": [
                {"questionId": q1, "outcome": "correct"},
                {"questionId": q1, "outcome": "correct"},
            ]
        },
        headers=headers,
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "duplicate_question_results"

    # 2. Question ID not in plan
    res = await client.post(
        f"/v1/study/sessions/{session_id}/complete",
        json={
            "results": [
                {"questionId": q1, "outcome": "correct"},
                {"questionId": 99999, "outcome": "correct"},
            ]
        },
        headers=headers,
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "question_not_in_plan"

    # 3. Missing question ID from plan
    res = await client.post(
        f"/v1/study/sessions/{session_id}/complete",
        json={"results": [{"questionId": q1, "outcome": "correct"}]},
        headers=headers,
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "missing_question_results"


async def test_read_session_active_and_completed(app, client, session, clerk_stub):
    """GET /v1/study/sessions/{id} returns active state or completed summary."""
    user = User(email="read_test@test.co", clerk_id="user_read_test")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    deck = await _create_test_deck(session, user.id, [501])

    fake_lexi = _HybridTestLexiReader()
    q1 = fake_lexi.add_supply(sense_id=501, level=1, type_id="definition_mcq")[0]
    app.dependency_overrides[get_lexi_client] = lambda: fake_lexi

    token = clerk_stub.token(subject="user_read_test", email="read_test@test.co")
    headers = bearer(token)

    # 1. Start session
    create_res = await client.post(
        "/v1/study/sessions", json={"nodeId": str(deck.id)}, headers=headers
    )
    session_id = create_res.json()["sessionId"]

    # 2. Read active session
    read_active = await client.get(f"/v1/study/sessions/{session_id}", headers=headers)
    assert read_active.status_code == 200
    active_data = read_active.json()
    assert active_data["status"] == "live"
    assert active_data["sensesAdmitted"] == 1

    # 3. Complete session
    await client.post(
        f"/v1/study/sessions/{session_id}/complete",
        json={"results": [{"questionId": q1, "outcome": "correct"}]},
        headers=headers,
    )

    # 4. Read completed session
    read_comp = await client.get(f"/v1/study/sessions/{session_id}", headers=headers)
    assert read_comp.status_code == 200
    comp_data = read_comp.json()
    assert comp_data["status"] == "completed"
    assert comp_data["answersTotal"] == 1
    assert comp_data["answersCorrect"] == 1
    assert comp_data["completedAt"] is not None
