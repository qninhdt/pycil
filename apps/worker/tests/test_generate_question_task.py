"""Shared question-task worker completion resolves every private delivery."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

from pycil.content.lexi_types import Question

from pycil_worker.jobs import generate_question


def _context(worker_engine):
    @asynccontextmanager
    async def session_factory():
        yield object()

    return {
        "session_factory": session_factory,
        "lexi_engine": worker_engine,
        "worker_id": "worker-a",
    }


async def test_shared_question_task_completes_deliveries(monkeypatch):
    task_id = uuid4()
    calls = []

    class Engine:
        async def generate_questions(self, word_id, sense_id, formats, n):
            assert (word_id, sense_id, formats, n) == (7, 41, ["definition_mcq"], 1)
            return [
                Question(
                    id=99,
                    word_id=7,
                    sense_id=41,
                    format="definition_mcq",
                    answer_kind="choice",
                    payload={},
                )
            ]

    async def claim_task(_session, seen_task_id, worker_id):
        assert (seen_task_id, worker_id) == (task_id, "worker-a")
        return SimpleNamespace(lease_token="token", lease_fence=3)

    async def complete_question_task(_session, seen_task_id, **kwargs):
        calls.append((seen_task_id, kwargs))
        return object()

    monkeypatch.setattr(generate_question.task_service, "claim_task", claim_task)
    monkeypatch.setattr(
        generate_question.task_service, "complete_question_task", complete_question_task
    )

    result = await generate_question.generate_question(
        _context(Engine()), str(task_id), 7, ["definition_mcq"], 1, None, 41
    )

    assert result == {
        "status": "done",
        "questions": [{"id": 99, "sense_id": 41, "format": "definition_mcq"}],
    }
    assert calls == [
        (
            task_id,
            {
                "lease_token": "token",
                "lease_fence": 3,
                "result": {"questions": [{"id": 99, "sense_id": 41, "format": "definition_mcq"}]},
            },
        )
    ]
