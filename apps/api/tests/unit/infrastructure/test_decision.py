import asyncio
import json
from typing import Annotated, Literal

import httpx
import pytest
from instructor.decisions import Noul, Question
from pydantic import BaseModel

from pycil.app.config import load_config
from pycil.infrastructure.llm import DecisionLLM, UsageRecorder
from pycil.infrastructure.retry import ProviderOutputError, ProviderTimeoutError


class Assessment(BaseModel):
    choice: Annotated[Literal["yes", "no"], Question(instructions="Choose for {{ text }}")]
    probability: Annotated[float, Noul(instructions="Is the claim true?")]


def response(*, choice="yes", probability=0.85, inputs=15):
    return {
        "answers": {
            "choice": {"type": "choice", "choice": choice},
            "probability": {"type": "noul", "noul": probability},
        },
        "usage": {"input_tokens": inputs, "output_tokens": 0},
    }


def client(http, *, retries=0, timeout=5):
    policy = load_config().vocabulary.provider.model_copy(
        update={"max_retries": retries, "timeout_seconds": timeout}
    )
    return DecisionLLM(
        policy, api_key="test", endpoint="https://decision.test/decisions", http_client=http
    )


async def test_native_decisions_render_questions_validate_answers_and_measure_usage():
    requests = []

    async def respond(request):
        requests.append(request)
        return httpx.Response(200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        decision_llm = client(http)
        with UsageRecorder() as recorder:
            result = await decision_llm.decide(Assessment, {"text": "sample context"})
            _, usage = recorder.finish(result)
        assert not http.is_closed
    assert result == Assessment(choice="yes", probability=0.85)
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    assert body["model"] == load_config().vocabulary.provider.decision_model
    assert requests[0].url == "https://decision.test/decisions"
    assert body["state"] == {"text": "sample context"}
    assert body["questions"]["choice"] == {
        "type": "choice",
        "instructions": "Choose for sample context",
        "criteria": {"yes": None, "no": None},
    }
    assert requests[0].headers["authorization"] == "Bearer test"
    assert requests[0].extensions["timeout"]["read"] == 5
    assert usage[0].input_tokens == 15 and usage[0].output_tokens == 0
    assert usage[0].model_id == decision_llm.client.model


@pytest.mark.parametrize("status, attempts", [(401, 1), (422, 1), (429, 2), (503, 2)])
async def test_decision_transport_retries_only_transient_statuses(status, attempts):
    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(status if len(calls) == 1 else 200, json=response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        decision_llm = client(http, retries=1)
        if attempts == 1:
            with pytest.raises(httpx.HTTPStatusError):
                await decision_llm.decide(Assessment, {"text": "example"})
        else:
            assert (await decision_llm.decide(Assessment, {"text": "example"})).choice == "yes"
    assert len(calls) == attempts


@pytest.mark.parametrize(
    "invalid", [{"choice": "outside"}, {"probability": 1.1}, {"probability": True}]
)
async def test_invalid_decision_answers_never_escape_native_validation_and_keep_usage(invalid):
    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, json=response(**invalid))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ProviderOutputError) as captured:
            await client(http, retries=1).decide(Assessment, {"text": "example"})
    assert len(calls) == 2
    assert captured.value.usage[0].input_tokens == 30


async def test_invalid_local_model_fails_before_transport_without_retry():
    class InvalidAssessment(BaseModel):
        unsupported: int

    def respond(request):
        pytest.fail("invalid question schema must not make a provider request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ValueError, match="Expected a string Literal"):
            await client(http, retries=1).decide(InvalidAssessment, {})


async def test_decision_deadline_cancels_and_joins_the_provider_request():
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def respond(request):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ProviderTimeoutError, match="model operation timed out") as captured:
            await client(http, timeout=0.02).decide(Assessment, {"text": "example"})
    assert started.is_set() and cleaned.is_set()
    assert captured.value.usage[0].input_tokens is None
