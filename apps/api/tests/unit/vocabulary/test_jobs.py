import asyncio
from types import SimpleNamespace

import pytest

from pycil.app.http import Problem
from pycil.vocabulary.enums import GenerationStage, JobState
from pycil.vocabulary.generation import jobs


def manager():
    config = SimpleNamespace(generation=SimpleNamespace(timeout_seconds=10, examples_per_sense=1))
    return jobs.Generations(None, None, None, None, config)


async def test_normalized_singleflight_and_ready_status_follow_completed_publication(monkeypatch):
    started, finish = asyncio.Event(), asyncio.Event()
    calls = 0

    async def pipeline(*args, **options):
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return SimpleNamespace(id=7, senses=[SimpleNamespace(id=8)])

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    try:
        first = await generations.submit("bank")
        await started.wait()
        second = await generations.submit(" BANK ")
        assert first["task_id"] == second["task_id"]
        assert generations.status(first["task_id"])["status"] is JobState.RUNNING
        finish.set()
        await generations.wait([first["task_id"]])
        result = generations.status(first["task_id"])
        assert calls == 1
        assert result["word_id"] == 7
        assert result["status"] is JobState.SUCCEEDED
        assert result["stage"] is GenerationStage.READY
    finally:
        await generations.close()


async def test_configured_deadline_cancels_and_joins_pipeline_before_failure(monkeypatch):
    cleaned = asyncio.Event()

    async def pipeline(*args, **options):
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    generations.config.generation.timeout_seconds = 0.01
    try:
        submitted = await generations.submit("bank")
        async with asyncio.timeout(1):
            await cleaned.wait()
            await asyncio.gather(*(task for _, task in generations.flights.values()))
        result = generations.status(submitted["task_id"])
        assert result["status"] is JobState.FAILED
        assert result["error"] == "generation_timeout" and result["word_id"] is None
        assert not generations.flights
    finally:
        await generations.close()


async def test_reference_identity_singleflight_does_not_merge_distinct_selections(monkeypatch):
    finish = asyncio.Event()

    async def reference(*args):
        return SimpleNamespace(id=args[-1])

    async def pipeline(*args, **options):
        await finish.wait()
        return SimpleNamespace(id=options["reference_id"], senses=[SimpleNamespace(id=8)])

    monkeypatch.setattr(jobs, "fetch_reference", reference)
    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    try:
        first = await generations.submit("bank", reference_id=11)
        same = await generations.submit(" BANK ", reference_id=11)
        other = await generations.submit("bank", reference_id=12)
        assert first["task_id"] == same["task_id"] != other["task_id"]
        finish.set()
        await generations.wait([first["task_id"], other["task_id"]])
        assert generations.status(first["task_id"])["word_id"] == 11
        assert generations.status(other["task_id"])["word_id"] == 12
    finally:
        await generations.close()


async def test_shutdown_cancels_and_joins_owned_work_before_returning(monkeypatch):
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def pipeline(*args, **options):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    await generations.submit("bank")
    await started.wait()
    await generations.close()
    assert cleaned.is_set()
    assert not generations.flights
    with pytest.raises(Problem) as failure:
        await generations.submit("bank")
    assert failure.value.status == 503


@pytest.mark.parametrize("target", ["", "bad\u200bword", "{unknown}"])
async def test_invalid_generation_selection_creates_no_job(target):
    generations = manager()
    try:
        with pytest.raises(Problem) as error:
            await generations.submit(target)
        assert error.value.code == "invalid_generation_selection"
        assert not generations.flights and not generations.results
    finally:
        await generations.close()


@pytest.mark.parametrize(
    "failure, expected",
    [
        ("timeout", "generation_timeout"),
        ("provider", "generation_failed"),
        ("empty", "generation_failed"),
    ],
)
async def test_failed_generation_never_reports_ready_and_can_be_retried(
    monkeypatch, failure, expected
):
    async def pipeline(*args, **options):
        if failure == "timeout":
            raise TimeoutError()
        if failure == "provider":
            raise RuntimeError("private provider detail")
        return SimpleNamespace(id=7, senses=[])

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    try:
        first = await generations.submit("bank")
        await generations.wait([first["task_id"]])
        result = generations.status(first["task_id"])
        assert result["status"] is JobState.FAILED
        assert result["stage"] is GenerationStage.WORD
        assert result["error"] == expected and result["word_id"] is None
        retry = await generations.submit("bank")
        assert retry["task_id"] != first["task_id"]
        await generations.wait([retry["task_id"]])
    finally:
        await generations.close()
