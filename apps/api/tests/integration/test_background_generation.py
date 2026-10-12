"""Singleflight spans Word publication, with bounded concurrent tasks."""

import asyncio
from types import SimpleNamespace

import pytest

from pycil.http import Problem
from pycil.vocabulary.api import GenerationRequest
from pycil.vocabulary.generation import Generations


class ControlledLexicon:
    def __init__(self):
        self.calls = self.active = self.peak = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def validate_reference(self, reference_id):
        await asyncio.sleep(0)

    async def generate_word(self, target, *, reference_id, **kwargs):
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.started.set()
        try:
            await self.release.wait()
            return SimpleNamespace(id=self.calls, senses=[SimpleNamespace(id=self.calls)])
        finally:
            self.active -= 1


async def test_same_reference_joins_one_task_and_status_reads_are_detached(config):
    lexicon = ControlledLexicon()
    manager = Generations(lexicon, config)
    try:
        requests = [
            GenerationRequest(reference_id="reference1", target=target)
            for target in ("run", "running", "run")
        ]
        results = await asyncio.gather(
            *(manager.submit(data.target, reference_id=data.reference_id) for data in requests)
        )
        assert len({result["task_id"] for result in results}) == 1
        await lexicon.started.wait()
        assert lexicon.calls == 1
        assert manager.status(results[0]["task_id"])["status"] == "RUNNING"
        result = manager.status(results[0]["task_id"])
        result["status"] = "FAILED"
        assert manager.status(results[0]["task_id"])["status"] == "RUNNING"
        task = manager.flights["reference1"][1]
        lexicon.release.set()
        await task
        assert manager.status(results[0]["task_id"])["status"] == "SUCCEEDED"
        assert manager.flights == {}
    finally:
        await manager.close()


async def test_128_jobs_run_in_parallel_and_shutdown_joins_them(config):
    lexicon = ControlledLexicon()
    manager = Generations(lexicon, config)
    await asyncio.gather(
        *(manager.submit("word", reference_id=f"reference{i}") for i in range(130))
    )
    async with asyncio.timeout(3):
        while lexicon.active < 128:
            await asyncio.sleep(0)
    assert lexicon.peak == lexicon.active == 128
    tasks = [task for _, task in manager.flights.values()]
    await manager.close()
    assert lexicon.active == 0 and all(task.done() for task in tasks)
    assert not manager.flights and not manager.results
    with pytest.raises(Problem, match="generation_unavailable"):
        await manager.submit("run", reference_id="reference1")


async def test_batch_wait_joins_owned_jobs_without_cancelling_on_disconnect(config):
    lexicon = ControlledLexicon()
    manager = Generations(lexicon, config)
    try:
        results = await asyncio.gather(
            *(manager.submit("word", reference_id=f"reference{i}") for i in range(3))
        )
        await lexicon.started.wait()
        waiter = asyncio.create_task(manager.wait([r["task_id"] for r in results]))
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        assert all(not t.cancelled() for _, t in manager.flights.values())
        lexicon.release.set()
        await manager.wait([r["task_id"] for r in results])
        assert all(manager.status(r["task_id"])["status"] == "SUCCEEDED" for r in results)
    finally:
        await manager.close()


async def test_word_only_generation_joins_case_variants_without_reference_selection(config):
    lexicon = ControlledLexicon()
    manager = Generations(lexicon, config)
    try:
        results = await asyncio.gather(
            *(manager.submit(word) for word in ("bank", "BANK", " bank "))
        )
        assert len({result["task_id"] for result in results}) == 1
        await lexicon.started.wait()
        assert lexicon.calls == 1
        lexicon.release.set()
        await manager.wait([results[0]["task_id"]])
        assert manager.status(results[0]["task_id"])["status"] == "SUCCEEDED"
    finally:
        await manager.close()
