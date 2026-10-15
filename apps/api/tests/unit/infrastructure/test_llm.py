import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
import structlog
from pydantic import BaseModel, Field

from pycil.infrastructure.llm import StructuredLLM, UsageRecorder
from pycil.infrastructure.observability import OperationOutcome
from pycil.infrastructure.retry import RefusedOutputError


class Answer(BaseModel):
    number: int = Field(gt=0)


def completion(content='{"number":1}', *, refusal=None, usage=None, finish="stop"):
    return {
        "id": "completion-1",
        "object": "chat.completion",
        "created": 1,
        "model": "actual-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content, "refusal": refusal},
            }
        ],
        "usage": usage,
    }


def policy(structured=True):
    return SimpleNamespace(
        model="requested-model",
        max_completion_tokens=100,
        timeout_seconds=5,
        structured_outputs=structured,
        reasoning_effort=None,
        temperature=None,
        max_retries=1,
        retry_min_seconds=0.01,
        retry_max_seconds=0.02,
    )


async def test_parsing_failure_keeps_failed_usage_and_retries_once():
    requests = []
    replies = [
        completion(
            '{"number":0}', usage={"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}
        ),
        completion(usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}),
    ]

    async def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=replies.pop(0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        with UsageRecorder() as recorder:
            result = await structured_llm.complete("Task rules", "untrusted input", Answer)
            value, usage = recorder.finish(result)
    assert value.number == 1
    assert len(requests) == 2
    assert usage[0].input_tokens == 12
    assert usage[0].output_tokens == 5
    assert usage[0].model_id == "actual-model"
    assert "number" in requests[1]["messages"][-1]["content"]
    assert requests[0]["messages"][1]["content"] == "untrusted input"


async def test_refusal_is_terminal_and_missing_usage_is_unknown():
    requests = []

    async def respond(request):
        requests.append(request)
        return httpx.Response(200, json=completion(None, refusal="refused"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        with pytest.raises(RefusedOutputError) as captured:
            await structured_llm.complete("rules", "input", Answer)
    assert len(requests) == 1
    assert captured.value.usage[0].input_tokens is None


async def test_cancelled_provider_attempt_is_observed_without_retry(monkeypatch):
    calls = 0

    async def respond(request):
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError()

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        with structlog.testing.capture_logs() as logs:
            monkeypatch.setattr("pycil.infrastructure.llm.logger", structlog.get_logger())
            with pytest.raises(asyncio.CancelledError):
                await structured_llm.complete("rules", "input", Answer)
    assert calls == 1
    attempts = [event for event in logs if event["event"] == "provider_operation_completed"]
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == OperationOutcome.CANCELLED
    assert attempts[0]["usage"][0]["input_tokens"] is None


@pytest.mark.parametrize("status, expected_attempts", [(401, 1), (422, 1), (429, 2), (503, 2)])
async def test_structured_transport_uses_one_retry_budget(status, expected_attempts):
    calls = []

    async def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, json={"error": {"message": "provider failure"}})
        return httpx.Response(200, json=completion())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        if expected_attempts == 1:
            from openai import APIStatusError

            with pytest.raises(APIStatusError) as captured:
                await structured_llm.complete("rules", "input", Answer)
            assert captured.value.status_code == status
        else:
            assert (await structured_llm.complete("rules", "input", Answer)).number == 1
        assert not http.is_closed
    assert len(calls) == expected_attempts


@pytest.mark.parametrize("structured", [True, False])
async def test_exhausted_validation_retains_every_attempt_and_never_returns_invalid_output(
    structured,
):
    from pycil.infrastructure.retry import ProviderOutputError

    calls = []

    async def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=completion(
                '{"number":0}',
                usage={"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(structured), api_key="test", base_url="https://provider.test", http_client=http
        )
        with pytest.raises(ProviderOutputError) as captured:
            await structured_llm.complete("rules", "input", Answer)
    assert len(calls) == 2
    assert captured.value.usage[0].input_tokens == 14
    assert captured.value.usage[0].output_tokens == 4
    if structured:
        assert calls[0]["response_format"]["type"] == "json_schema"
    else:
        assert "response_format" not in calls[0]
        assert "json" in calls[0]["messages"][-1]["content"].lower()


@pytest.mark.parametrize("finish, refusal", [("content_filter", None), ("stop", "refused")])
async def test_refusal_with_valid_json_is_still_terminal(finish, refusal):
    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, json=completion(refusal=refusal, finish=finish))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        with pytest.raises(RefusedOutputError):
            await structured_llm.complete("rules", "input", Answer)
    assert len(calls) == 1


async def test_truncated_output_uses_native_instructor_failure_and_keeps_usage():
    from pycil.infrastructure.retry import ProviderOutputError

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=completion(
                finish="length",
                usage={"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        with pytest.raises(ProviderOutputError) as captured:
            await structured_llm.complete("rules", "input", Answer)
    assert len(calls) == 1
    assert captured.value.usage[0].input_tokens == 7


async def test_missing_retry_usage_never_becomes_a_fabricated_complete_total():
    replies = [
        completion('{"number":0}'),
        completion(usage={"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}),
    ]

    async def respond(request):
        return httpx.Response(200, json=replies.pop(0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        with UsageRecorder() as recorder:
            result = await structured_llm.complete("rules", "input", Answer)
            _, usage = recorder.finish(result)
    assert result.number == 1 and not replies
    assert usage[0].input_tokens is usage[0].output_tokens is None


async def test_cancelling_structured_backoff_prevents_another_request():
    failed = asyncio.Event()
    calls = []

    async def respond(request):
        calls.append(request)
        failed.set()
        return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        task = asyncio.create_task(structured_llm.complete("rules", "input", Answer))
        try:
            await failed.wait()
            # The request has returned; the native retry operation yields during backoff.
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert len(calls) == 1


async def test_structured_deadline_cancels_request_and_preserves_timeout_classification():
    from pycil.infrastructure.retry import ProviderOutputError, ProviderTimeoutError, retryable

    calls = []
    cleaned = asyncio.Event()

    async def respond(request):
        calls.append(request)
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    settings = policy()
    settings.timeout_seconds = 0.02
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            settings, api_key="test", base_url="https://provider.test", http_client=http
        )
        with pytest.raises(ProviderTimeoutError, match="model operation timed out") as captured:
            await structured_llm.complete("rules", "input", Answer)
    assert len(calls) == 1 and cleaned.is_set()
    assert isinstance(captured.value, ProviderOutputError)
    assert isinstance(captured.value, TimeoutError)
    assert not retryable(captured.value)
    assert captured.value.usage[0].input_tokens is None


async def test_concurrent_operations_on_shared_transport_keep_usage_isolated():
    entered = 0
    both_entered = asyncio.Event()

    async def respond(request):
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await both_entered.wait()
        tokens = int(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(
            200,
            json=completion(usage={"prompt_tokens": tokens, "completion_tokens": 2}),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )

        async def generate(tokens):
            with UsageRecorder() as recorder:
                result = await structured_llm.complete("rules", str(tokens), Answer)
                return recorder.finish(result)

        first, second = await asyncio.wait_for(asyncio.gather(generate(7), generate(19)), timeout=5)
    assert first[0].number == second[0].number == 1
    assert len(first[1]) == len(second[1]) == 1
    assert first[1][0].input_tokens == 7
    assert second[1][0].input_tokens == 19


async def test_native_retry_logs_do_not_expose_model_output(caplog):
    from pycil.infrastructure.retry import ProviderOutputError

    async def respond(request):
        return httpx.Response(200, json=completion('{"number":"private-model-output-marker"}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        structured_llm = StructuredLLM(
            policy(), api_key="test", base_url="https://provider.test", http_client=http
        )
        with pytest.raises(ProviderOutputError):
            await structured_llm.complete("private-prompt-marker", "private-answer-marker", Answer)
    assert "private-model-output-marker" not in caplog.text
    assert "private-prompt-marker" not in caplog.text
    assert "private-answer-marker" not in caplog.text
