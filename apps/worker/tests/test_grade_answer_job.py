"""Hermetic worker behavior tests for terminal grading delivery."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pycil.learning.infra.models import GradeStatus

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


async def test_grade_answer_returns_the_settled_verdict(monkeypatch, worker_context):
    """A settled verdict reports itself, and reports that no task consumed it.

    This used to assert on a direct publish to an owner-scoped grading channel. The
    subscribe proxy admits only ``async:<uuid>``, so that channel had no subscriber
    and the assertion proved delivery that could not happen. The durable snapshot is
    the delivery path, and ``task`` is what says whether one was found.
    """
    outcome = SimpleNamespace(
        response_id=uuid4(), sense_id=42, is_correct=True, grade_score=1.0,
        grade_feedback="ok", mastery_before=10, mastery_after=20,
        render_format="free_text", reveal=None,
    )

    async def resolve(*args):
        return outcome

    async def no_task(*args, **kwargs):
        return None

    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)
    monkeypatch.setattr(grade_answer.task_service, "find_live_task", no_task)

    result = await grade_answer.grade_answer_v1(worker_context, "owner", str(outcome.response_id))

    assert result == {"status": "graded", "is_correct": True, "task": "no-task"}


async def test_reconciled_grade_converges_the_task_snapshot(monkeypatch, worker_context):
    """A grade that arrives through the reconciler must settle the durable task.

    reconcile_pending_grades re-enqueues grade_answer_v1 by RESPONSE id, so this
    path has no task id. It used to publish only to the owner-scoped grading
    channel — which the subscribe proxy denies — and leave the AsyncTask QUEUED
    forever, so the snapshot the client watches disagreed with a verdict that was
    already durably applied.
    """
    response_id = uuid4()
    task_id = uuid4()
    outcome = SimpleNamespace(
        response_id=response_id, sense_id=7, is_correct=False, grade_score=0.25,
        grade_feedback="not quite", mastery_before=30, mastery_after=28,
        render_format="free_text", reveal={"answer": "x"},
    )
    looked_up: list[tuple[str, str]] = []
    transitions: list[dict] = []

    async def resolve(*args):
        return outcome

    async def find_live_task(session, *, kind, work_key):
        looked_up.append((kind, work_key))
        return SimpleNamespace(id=task_id)

    async def claim_task(session, tid, owner, **kwargs):
        assert tid == task_id
        return SimpleNamespace(id=task_id, lease_token="token", lease_fence=3)

    async def transition_task(session, tid, **kwargs):
        transitions.append({"task_id": tid, **kwargs})
        return True

    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)
    monkeypatch.setattr(grade_answer.task_service, "find_live_task", find_live_task)
    monkeypatch.setattr(grade_answer.task_service, "claim_task", claim_task)
    monkeypatch.setattr(grade_answer.task_service, "transition_task", transition_task)

    result = await grade_answer.grade_answer_v1(worker_context, "owner", str(response_id))

    assert result["status"] == "graded"
    assert result["task"] == "converged"
    # Located through the SAME work key that created the task, not a guessed id.
    assert looked_up == [("grading", f"grading:{response_id}")]
    settled = transitions[0]
    assert settled["status"] is grade_answer.AsyncTaskStatus.SUCCEEDED
    assert settled["lease_token"] == "token"
    assert settled["lease_fence"] == 3
    # The snapshot carries the verdict the client is waiting on, camelCase.
    assert settled["result"]["isCorrect"] is False
    assert settled["result"]["masteryAfter"] == 28
    assert settled["result"]["responseId"] == str(response_id)


async def test_grade_convergence_failure_does_not_fail_the_grade(monkeypatch, worker_context):
    """The verdict is already durably applied; the snapshot is only an accelerator."""
    response_id = uuid4()
    outcome = SimpleNamespace(
        response_id=response_id, sense_id=1, is_correct=True, grade_score=1.0,
        grade_feedback="", mastery_before=1, mastery_after=2,
        render_format="free_text", reveal=None,
    )

    async def resolve(*args):
        return outcome

    async def find_live_task(session, *, kind, work_key):
        return SimpleNamespace(id=uuid4())

    async def claim_task(*args, **kwargs):
        return None  # another worker holds the lease

    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)
    monkeypatch.setattr(grade_answer.task_service, "find_live_task", find_live_task)
    monkeypatch.setattr(grade_answer.task_service, "claim_task", claim_task)

    result = await grade_answer.grade_answer_v1(worker_context, "owner", str(response_id))

    assert result["status"] == "graded"
    assert result["task"] == "not-claimable"


async def test_grade_answer_retry_settles_nothing_a_second_time(monkeypatch, worker_context):
    """An arq redelivery of an already-terminal response must be a no-op.

    `apply_verdict` returning None means the response was already settled (or is
    still pending), so the job reports `duplicate` and touches nothing further.
    """

    async def resolve(*args):
        return None

    monkeypatch.setattr(grade_answer.service, "apply_verdict", resolve)

    result = await grade_answer.grade_answer_v1(worker_context, "owner", str(uuid4()))
    assert result == {"status": "duplicate"}


async def test_grade_answer_task_persists_camel_case_snapshot(monkeypatch, worker_context):
    task_id = uuid4()
    response_id = uuid4()
    outcome = SimpleNamespace(
        response_id=response_id, sense_id=42, is_correct=True, grade_score=1.0,
        grade_feedback="ok", mastery_before=10, mastery_after=20,
        render_format="free_text", reveal=None,
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
        "renderFormat": "free_text", "reveal": None,
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
        render_format="single_choice",
        reveal={"correct_index": 1, "correct_option": "answer"},
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
        "renderFormat": "single_choice",
        "reveal": {"correct_index": 1, "correct_option": "answer"},

    }