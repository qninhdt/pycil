"""Question supply warm-up: prepare_questions warms per-word demand."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from arq import Retry
from lexi_ai.contracts import Flashcard, PresentedQuestion

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
