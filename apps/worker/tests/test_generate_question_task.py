"""Question supply warm-up: prepare_questions warms per-word demand."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from arq import Retry
from lexi_ai.contracts import Flashcard, PresentedQuestion
from pycil.tasks.infra.models import AsyncTaskStatus

from pycil_worker.jobs import generate_question

pytestmark = pytest.mark.asyncio


def _context(engine, reader=None):
    @asynccontextmanager
    async def session_factory():
        yield object()

    return {
        "session_factory": session_factory,
        "lexi_engine": engine,
        "lexi_reader": reader or object(),
        "worker_id": "worker-a",
    }


async def test_prepare_questions_warms_supply_grouped_by_word():
    prepared = []

    class Reader:
        async def retrieve_exposure(self, sense_id):
            return PresentedQuestion(
                question_id=f"exposure:{sense_id}",
                word_id="7",
                sense_id=str(sense_id),
                type_id="flashcard",
                difficulty_level=0,
                interaction="exposure",
                render=Flashcard(word="run", definition="move"),
            )

    class Engine:
        async def prepare_questions(self, word_id, demands):
            prepared.append(
                (word_id, [(d.sense_id, d.difficulty_level, d.expected_count) for d in demands])
            )
            return SimpleNamespace(
                produced={(int(d.sense_id), d.difficulty_level): d.expected_count for d in demands}
            )

    result = await generate_question.prepare_questions(
        _context(Engine(), Reader()), "owner", [[41, 1, 2], [41, 2, 1]]
    )
    assert result["status"] == "done"
    assert result["prepared"] == 3  # 2 + 1
    assert prepared[0][0] == 7  # grouped under resolved word_id


async def test_prepare_questions_best_effort_skips_unresolvable_sense():
    class Reader:
        async def retrieve_exposure(self, sense_id):
            raise LookupError("missing sense")

    class Engine:
        async def prepare_questions(self, word_id, demands):  # pragma: no cover
            raise AssertionError("should not prepare for unresolved sense")

    result = await generate_question.prepare_questions(
        _context(Engine(), Reader()), "owner", [[41, 1, 2]]
    )
    assert result == {"status": "done", "prepared": 0}


async def test_prepare_questions_retries_transient_provider_failure():
    class Reader:
        async def retrieve_exposure(self, sense_id):
            return PresentedQuestion(
                question_id=f"exposure:{sense_id}", word_id="7", sense_id=str(sense_id),
                type_id="flashcard", difficulty_level=0, interaction="exposure",
                render=Flashcard(word="run", definition="move"),
            )

    class Engine:
        async def prepare_questions(self, word_id, demands):
            raise RuntimeError("provider unavailable")

    context = _context(Engine(), Reader())
    context["job_try"] = 1
    with pytest.raises(Retry):
        await generate_question.prepare_questions(context, "owner", [[41, 1, 1]])


async def test_prepare_questions_reports_terminal_retry_exhaustion():
    class Reader:
        async def retrieve_exposure(self, sense_id):
            raise RuntimeError("transient lookup failure")

    context = _context(object(), Reader())
    context["job_try"] = 2
    result = await generate_question.prepare_questions(context, "owner", [[41, 1, 1]])
    assert result == {"status": "failed", "prepared": 0, "failed": 1}


# --- the durable wrapper -----------------------------------------------------
#
# What the registry adds is not the warm-up but its *announcement*: every
# transition writes an outbox row that reaches `async:{task_id}`, which is the
# only channel the subscribe proxy admits. The learner's client waits on that and
# no longer re-calls `/next`, so a task left un-transitioned is not a slow session
# but a stopped one — which is why both outcomes below settle.


class _Recorder:
    """Stands in for the task service, recording the transition rather than the row."""

    def __init__(self, claim=SimpleNamespace(lease_token="token", lease_fence=3)):
        self.claim = claim
        self.transitions: list[dict] = []

    async def claim_task(self, _session, _task_id, _owner):
        return self.claim

    async def transition_task(self, _session, task_id, **kwargs):
        self.transitions.append({"task_id": task_id, **kwargs})
        return SimpleNamespace(id=task_id)


def _settling_context(monkeypatch, recorder, engine, reader=None):
    monkeypatch.setattr(generate_question.task_service, "claim_task", recorder.claim_task)
    monkeypatch.setattr(
        generate_question.task_service, "transition_task", recorder.transition_task
    )
    return _context(engine, reader)


def _reader(word_id="7"):
    class Reader:
        async def retrieve_exposure(self, sense_id):
            return PresentedQuestion(
                question_id=f"exposure:{sense_id}", word_id=word_id, sense_id=str(sense_id),
                type_id="flashcard", difficulty_level=0, interaction="exposure",
                render=Flashcard(word="run", definition="move"),
            )

    return Reader()


async def test_a_warmed_supply_task_settles_so_the_waiting_client_is_told(monkeypatch):
    class Engine:
        async def prepare_questions(self, word_id, demands):
            return SimpleNamespace(produced={"single_choice": 2})

    recorder = _Recorder()
    context = _settling_context(monkeypatch, recorder, Engine(), _reader())

    task_id = uuid4()
    result = await generate_question.prepare_questions_task(
        context, str(task_id), "owner", [[41, 1, 1]]
    )

    assert result == {"status": "done", "prepared": 2}
    assert len(recorder.transitions) == 1
    settled = recorder.transitions[0]
    assert settled["status"] is AsyncTaskStatus.SUCCEEDED
    # The fence is what makes a superseded lease unable to settle the task; passing
    # it through is the difference between idempotent and merely usually-correct.
    assert settled["lease_token"] == "token" and settled["lease_fence"] == 3


async def test_an_exhausted_warm_up_settles_too_rather_than_hanging_the_session(monkeypatch):
    """A failure the client can see beats a subscription that never resolves.

    The learner is watching this task and nothing else. Leaving it RUNNING would
    hang the session on an event that is never coming — strictly worse than the
    poll it replaced, which at least gave up.
    """
    class Reader:
        async def retrieve_exposure(self, sense_id):
            raise RuntimeError("transient lookup failure")

    recorder = _Recorder()
    context = _settling_context(monkeypatch, recorder, object(), Reader())
    context["job_try"] = 2  # past the retry budget, so the warm-up reports failure

    result = await generate_question.prepare_questions_task(
        context, str(uuid4()), "owner", [[41, 1, 1]]
    )

    assert result["status"] == "failed"
    assert recorder.transitions[0]["status"] is AsyncTaskStatus.FAILED
    assert recorder.transitions[0]["error_code"] == "question_preparation_exhausted"


async def test_a_lost_claim_runs_no_warm_up_at_all(monkeypatch):
    """The claim is what makes a redelivery cheap instead of a second bill.

    Both arq's retry and the reconciler's re-enqueue land here for the same task.
    Only one wins the fenced lease; the other must not re-run the generation, which
    is the expensive half.
    """
    warmed = False

    class Engine:
        async def prepare_questions(self, word_id, demands):
            nonlocal warmed
            warmed = True
            return SimpleNamespace(produced={})

    recorder = _Recorder(claim=None)
    context = _settling_context(monkeypatch, recorder, Engine(), _reader())

    result = await generate_question.prepare_questions_task(
        context, str(uuid4()), "owner", [[41, 1, 1]]
    )

    assert result == {"status": "duplicate"}
    assert warmed is False, "a duplicate delivery re-ran the generation it should have skipped"
    assert recorder.transitions == []


async def test_an_arq_retry_keeps_the_lease_instead_of_settling_the_task(monkeypatch):
    """`Retry` is arq's redelivery signal, not an outcome.

    Transitioning on it would settle a task still being worked, and the client would
    be told supply finished while the worker was about to try again.
    """
    class Engine:
        async def prepare_questions(self, word_id, demands):
            raise RuntimeError("provider unavailable")

    recorder = _Recorder()
    context = _settling_context(monkeypatch, recorder, Engine(), _reader())
    context["job_try"] = 1  # inside the retry budget

    with pytest.raises(Retry):
        await generate_question.prepare_questions_task(
            context, str(uuid4()), "owner", [[41, 1, 1]]
        )

    assert recorder.transitions == [], "a redelivery signal settled the task"
