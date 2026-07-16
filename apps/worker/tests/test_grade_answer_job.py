"""Hermetic worker behavior tests for terminal grading delivery."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pycil_worker.jobs import grade_answer


@pytest.fixture
def worker_context():
    @asynccontextmanager
    async def session_factory():
        yield object()

    return {"session_factory": session_factory, "lexi_client": object()}


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
    assert published[0][1].to_dict()["mastery_after"] == 20


async def test_grade_answer_retry_does_not_republish(monkeypatch, worker_context):
    async def resolve(*args):
        return None

    async def publish(*args):  # pragma: no cover - must never be reached
        raise AssertionError("terminal retry was published")

    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)
    monkeypatch.setattr(grade_answer.realtime, "publish_grading", publish)

    result = await grade_answer.grade_answer(worker_context, "owner", str(uuid4()))
    assert result == {"status": "duplicate"}
