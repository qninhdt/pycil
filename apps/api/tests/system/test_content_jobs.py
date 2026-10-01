"""A post-response content task runs in the API process and exposes a receipt.

The API calls the LLM gateway over HTTP after returning a task id, writes a Lexi
row, and serves the result from an owner-scoped Redis receipt.

The gateway is the only substitution, and it is a protocol substitution: the API's
own OpenAI-compatible client parses its responses, so a wrong wire shape fails here
rather than passing.

The receipt's status vocabulary is the product's: `queued`, `running`, and the three
ways a job stops — `done`, `failed`, `expired`.
"""

import asyncio

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]

TERMINAL = {"done", "failed", "expired"}


async def _settled(caller, job_id: str, *, timeout: float = 90.0) -> dict:
    """Read the receipt until the background callback finishes.

    Polling the *receipt* rather than resubmitting the work is the product's own rule:
    the generation is asynchronous and the job id is the handle to its progress. A
    journey that re-posted instead would start a second generation and pay for it.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    last: dict = {}
    while asyncio.get_running_loop().time() < deadline:
        last = await caller.ok("GET", f"/v1/jobs/{job_id}")
        if last["status"] in TERMINAL:
            return last
        await asyncio.sleep(0.25)
    raise AssertionError(f"job never settled: {last}")


async def test_a_word_generation_accepted_by_the_api_finishes_in_background(actor):
    caller = actor.new()
    created = await caller.ok("POST", "/v1/word-generations", json={"query": "resilient"})

    receipt = await _settled(caller, created["taskId"])

    assert receipt["status"] == "done", receipt
    # The result names the Lexi rows the worker created, so the job really wrote.
    assert receipt["result"]["senseIds"], receipt


async def test_a_receipt_is_readable_only_by_the_learner_who_queued_it(actor):
    """A job id is not a capability: another learner guessing one gets a 404."""
    owner = actor.new()
    created = await owner.ok("POST", "/v1/word-generations", json={"query": "tenacious"})

    stranger = actor.new()
    response = await stranger.get(f"/v1/jobs/{created['taskId']}")

    assert response.status_code == 404
    assert response.json()["code"] == "job_not_found"


async def test_an_unknown_job_is_the_same_404_as_someone_elses(actor):
    """Indistinguishable on purpose: otherwise the route enumerates other learners."""
    caller = actor.new()

    unknown = await caller.get("/v1/jobs/does-not-exist")
    stranger = actor.new()
    created = await stranger.ok("POST", "/v1/word-generations", json={"query": "opaque"})
    other = await caller.get(f"/v1/jobs/{created['taskId']}")

    assert unknown.status_code == other.status_code == 404
    assert unknown.json()["code"] == other.json()["code"] == "job_not_found"
