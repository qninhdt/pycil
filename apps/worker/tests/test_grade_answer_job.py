"""Hermetic worker behavior tests for terminal grading delivery."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pycil.learning.models import GradeStatus

from pycil_worker.jobs import grade_answer


@pytest.fixture
def worker_context():
    @asynccontextmanager
    async def session_factory():
        yield object()

    return {
        "session_factory": session_factory,
        "lexi_reader": object(),
        "lexi_engine": object(),
    }


async def test_grade_answer_publishes_terminal_verdict(monkeypatch, worker_context):
    outcome = SimpleNamespace(
        response_id=uuid4(), sense_id=42, is_correct=True, grade_score=1.0,
        grade_feedback="ok", mastery_before=10, mastery_after=20,
    )
    published = []

    async def resolve(*args):
        return outcome

    async def publish(owner_uid, event):
        published.append((owner_uid, event))

    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)
    monkeypatch.setattr(grade_answer.realtime, "publish_grading", publish)

    result = await grade_answer.grade_answer(worker_context, "owner", str(outcome.response_id))

    assert result == {"status": "graded", "is_correct": True}
    assert published[0][1].to_dict()["masteryAfter"] == 20


async def test_grade_answer_retry_does_not_republish(monkeypatch, worker_context):
    async def resolve(*args):
        return None

    async def publish(*args):  # pragma: no cover - must never be reached
        raise AssertionError("terminal retry was published")

    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)
    monkeypatch.setattr(grade_answer.realtime, "publish_grading", publish)

    result = await grade_answer.grade_answer(worker_context, "owner", str(uuid4()))
    assert result == {"status": "duplicate"}


async def test_grade_answer_task_persists_camel_case_snapshot(monkeypatch, worker_context):
    task_id = uuid4()
    response_id = uuid4()
    outcome = SimpleNamespace(
        response_id=response_id, sense_id=42, is_correct=True, grade_score=1.0,
        grade_feedback="ok", mastery_before=10, mastery_after=20,
    )
    transitions = []

    async def claim_task(_session, seen_task_id, _worker_id):
        assert seen_task_id == task_id
        return SimpleNamespace(lease_token="token", lease_fence=1)

    async def resolve(*_args):
        return outcome

    async def transition_task(_session, seen_task_id, **kwargs):
        transitions.append((seen_task_id, kwargs))
        return object()

    monkeypatch.setattr(grade_answer.task_service, "claim_task", claim_task)
    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)
    monkeypatch.setattr(grade_answer.task_service, "transition_task", transition_task)

    result = await grade_answer.grade_answer_task(
        worker_context, str(task_id), "owner", str(response_id)
    )

    assert result == {"status": "graded", "is_correct": True}
    assert transitions[0][1]["result"] == {
        "responseId": str(response_id), "senseId": 42, "isCorrect": True,
        "gradeScore": 1.0, "gradeFeedback": "ok", "masteryBefore": 10, "masteryAfter": 20,
    }


async def test_grade_task_recovers_after_verdict_persisted_before_worker_crash(monkeypatch):
    task_id = uuid4()
    response_id = uuid4()
    response = SimpleNamespace(
        id=response_id,
        sense_id=42,
        is_correct=True,
        grade_status=GradeStatus.graded,
        grade_score=1.0,
        grade_feedback="ok",
        mastery_before=10,
        mastery_after=20,
    )
    transitions = []

    class Session:
        async def get(self, model, identity):
            assert model is grade_answer.Response
            assert identity == response_id
            return response

    @asynccontextmanager
    async def session_factory():
        yield Session()

    async def claim_task(_session, seen_task_id, _worker_id):
        assert seen_task_id == task_id
        return SimpleNamespace(lease_token="token", lease_fence=1)

    async def resolve(*_args):
        return None

    async def transition_task(_session, seen_task_id, **kwargs):
        transitions.append((seen_task_id, kwargs))
        return object()

    monkeypatch.setattr(grade_answer.task_service, "claim_task", claim_task)
    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)
    monkeypatch.setattr(grade_answer.task_service, "transition_task", transition_task)

    result = await grade_answer.grade_answer_task(
        {"session_factory": session_factory, "lexi_reader": object(), "lexi_engine": object()},
        str(task_id),
        "owner",
        str(response_id),
    )

    assert result == {"status": "graded", "is_correct": True}
    assert transitions[0][1]["status"].value == "succeeded"
    assert transitions[0][1]["result"] == {
        "responseId": str(response_id),
        "senseId": 42,
        "isCorrect": True,
        "gradeScore": 1.0,
        "gradeFeedback": "ok",
        "masteryBefore": 10,
        "masteryAfter": 20,
    }
