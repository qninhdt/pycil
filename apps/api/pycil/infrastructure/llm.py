"""Unified LLM infrastructure with Instructor:
structured transport, decision models, prompts, and usage.
"""

import asyncio
import logging
import re
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache, reduce
from time import perf_counter
from types import TracebackType
from typing import Annotated, Any, Literal, Self, cast

import httpx
import instructor
from instructor.decisions import Choice, Question
from instructor.decisions.client import AsyncDecisionsClient
from instructor.v2.core.client import AsyncInstructor
from instructor.v2.core.errors import InstructorError, InstructorRetryException
from instructor.v2.core.mode import Mode
from jinja2 import Environment, PackageLoader, StrictUndefined
from openai import APIError
from pydantic import BaseModel, ConfigDict, create_model
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from pycil.infrastructure.observability import OperationOutcome, get_logger
from pycil.infrastructure.retry import (
    ProviderOutputError,
    ProviderTimeoutError,
    RefusedOutputError,
    retryable,
)
from pycil.vocabulary.config import VocabularyPolicy

logger = get_logger(__name__)


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    model_id: str | None
    input_tokens: int | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None
    output_tokens: int | None


records: ContextVar[list[TokenUsage] | None] = ContextVar("provider_usage", default=None)


def field(value: Any, name: str, default: Any = None) -> Any:
    return (
        cast(Mapping[str, Any], value).get(name, default)
        if isinstance(value, Mapping)
        else getattr(value, name, default)
    )


def count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def openai_usage(response: Any, model_override: str | None = None) -> TokenUsage:
    """Extract standard TokenUsage from a ChatCompletion, raw dict, or exception completion."""
    if response is None:
        return TokenUsage(
            model_id=model_override,
            input_tokens=None,
            output_tokens=None,
            cache_read_tokens=None,
            cache_write_tokens=None,
        )
    usage: Any = field(response, "usage")
    details = field(usage, "prompt_tokens_details", field(usage, "input_tokens_details", {}))
    inputs = count(
        field(
            usage,
            "prompt_tokens",
            field(usage, "input_tokens", field(usage, "input_tokens_total")),
        )
    )
    outputs = count(
        field(
            usage,
            "completion_tokens",
            field(usage, "output_tokens", field(usage, "output_tokens_total")),
        )
    )
    output_details = field(
        usage, "completion_tokens_details", field(usage, "output_tokens_details", {})
    )
    reasoning = count(field(output_details, "reasoning_tokens"))
    if inputs is not None and outputs is not None and reasoning is not None:
        if reasoning > 0 and count(field(usage, "total_tokens")) == inputs + outputs + reasoning:
            outputs += reasoning
    model = field(response, "model") or model_override
    return TokenUsage(
        model_id=model if isinstance(model, str) and model.strip() else None,
        input_tokens=inputs,
        output_tokens=outputs,
        cache_read_tokens=count(field(details, "cached_tokens", field(usage, "cache_read_tokens"))),
        cache_write_tokens=count(
            field(details, "cache_write_tokens", field(usage, "cache_write_tokens"))
        ),
    )


def record(usage: TokenUsage) -> None:
    if (active := records.get()) is not None:
        active.append(usage)


def merge_usage(values: list[TokenUsage]) -> list[TokenUsage]:
    grouped: dict[str | None, TokenUsage] = {}
    for value in values:
        if value.model_id not in grouped:
            grouped[value.model_id] = value
            continue
        previous = grouped[value.model_id]
        counts: dict[str, int | None] = {}
        for name in TokenUsage.model_fields:
            if name == "model_id":
                continue
            a, b = getattr(previous, name), getattr(value, name)
            counts[name] = None if a is None or b is None else a + b
        grouped[value.model_id] = TokenUsage(model_id=value.model_id, **counts)
    return [grouped[key] for key in sorted(grouped, key=lambda key: (key is None, key or ""))]


class UsageRecorder:
    def __enter__(self) -> Self:
        self.records: list[TokenUsage] = []
        self.token = records.set(self.records)
        return self

    def __exit__(
        self,
        _kind: type[BaseException] | None,
        error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        records.reset(self.token)
        if error is not None:
            cast(Any, error).usage = merge_usage(self.records)

    def finish(self, value: Any) -> tuple[Any, list[TokenUsage]]:
        return value, merge_usage(self.records)


environment = Environment(
    loader=PackageLoader("pycil", ""),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)
environment.policies["json.dumps_kwargs"] = {
    "sort_keys": True,
    "separators": (",", ":"),
}
ROLE = re.compile(r"\{#\s*(system|user)\s*#\}")


@cache
def _prompt(name: str):
    if environment.loader is None:
        raise RuntimeError("Template loader is not configured")
    source, _filename, _current = environment.loader.get_source(environment, name)
    markers = list(ROLE.finditer(source))
    if [marker[1] for marker in markers] != ["system", "user"] or source[
        : markers[0].start()
    ].strip():
        raise ValueError("prompt must declare system then user exactly once")
    return environment.from_string(
        source[markers[0].end() : markers[1].start()]
    ), environment.from_string(source[markers[1].end() :])


def render_prompt(name: str, **context: Any) -> tuple[str, str]:
    instruction, data = _prompt(name)
    return instruction.render(**context).strip(), data.render(**context).strip()


def choice_model[T: BaseModel](
    name: str,
    base: type[T],
    field_name: str,
    instructions: str,
    criteria: Mapping[str, str],
) -> type[T]:
    annotations: list[Any] = [
        Annotated[Literal[value], Choice(description=description)]
        for value, description in criteria.items()
    ]
    options: Any = reduce(lambda left, right: left | right, annotations)
    fields: dict[str, Any] = {
        field_name: (Annotated[options, Question(instructions=instructions)], ...)
    }
    return create_model(name, __base__=base, **fields)


class _ProviderCall:
    def __init__(self, model: str, operation: str):
        self.model = model
        self.operation = operation
        self.measurements: list[TokenUsage] = []
        self.attempts = 0
        self.refused = False

    def start_attempt(self) -> None:
        self.attempts += 1
        self.refused = False

    @contextmanager
    def observe(self) -> Generator[_ProviderCall]:
        started = perf_counter()
        token = current_call.set(self)
        outcome, category = OperationOutcome.SUCCEEDED, None
        error = None
        try:
            yield self
        except BaseException as exc:
            error = (
                ProviderTimeoutError("model operation timed out")
                if isinstance(exc, TimeoutError)
                else exc
            )
            outcome = (
                OperationOutcome.CANCELLED
                if isinstance(exc, asyncio.CancelledError)
                else OperationOutcome.FAILED
            )
            category = type(exc).__name__
            if error is not exc:
                raise error from None
            raise
        finally:
            current_call.reset(token)
            for _ in range(self.attempts - len(self.measurements)):
                self.measurements.append(openai_usage(None, self.model))
            for measured in self.measurements:
                record(measured)
            usage = merge_usage(self.measurements)
            if error is not None:
                cast(Any, error).usage = usage
            logger.info(
                "provider_operation_completed",
                operation=self.operation,
                requested_model=self.model,
                attempts=self.attempts,
                outcome=outcome,
                error_type=category,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                usage=[value.model_dump() for value in usage],
            )


current_call: ContextVar[_ProviderCall | None] = ContextVar("provider_call", default=None)


def _safe_instructor_log(entry: logging.LogRecord) -> bool:
    if (call := current_call.get()) is not None:
        # Instructor's retry diagnostics include raw model output in validation errors.
        entry.msg = "instructor_retry_event operation=%s attempts=%s"
        entry.args = (call.operation, call.attempts)
        entry.exc_info = entry.exc_text = entry.stack_info = None
    return True


async def _start_request(_request: httpx.Request) -> None:
    if (call := current_call.get()) is not None:
        call.start_attempt()


async def _measure_response(response: httpx.Response) -> None:
    if (call := current_call.get()) is None:
        return
    await response.aread()
    try:
        raw = response.json()
    except ValueError:
        raw = None
    # Read each HTTP response before Instructor replaces usage with cumulative totals.
    call.measurements.append(openai_usage(raw, call.model))
    choices = field(raw, "choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = cast(dict[str, Any], choices[0])
        message = choice.get("message")
        call.refused = bool(
            isinstance(message, dict)
            and field(message, "refusal")
            or choice.get("finish_reason") == "content_filter"
        )


def _instrument(http: httpx.AsyncClient) -> None:
    retry_logger = logging.getLogger("instructor.v2.retry")
    if _safe_instructor_log not in retry_logger.filters:
        retry_logger.addFilter(_safe_instructor_log)
    if _start_request not in http.event_hooks["request"]:
        http.event_hooks["request"].append(_start_request)
    if _measure_response not in http.event_hooks["response"]:
        http.event_hooks["response"].append(_measure_response)


def _retrying(
    policy: VocabularyPolicy,
    predicate: Callable[[BaseException], bool] = retryable,
) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(policy.max_retries + 1),
        wait=wait_exponential(multiplier=policy.retry_min_seconds, max=policy.retry_max_seconds),
        retry=retry_if_exception(predicate),
        reraise=True,
    )


class StructuredLLM:
    def __init__(
        self,
        policy: VocabularyPolicy,
        *,
        api_key: str,
        base_url: str,
        http_client: httpx.AsyncClient,
    ):
        self.policy = policy
        _instrument(http_client)
        self.client: AsyncInstructor = instructor.from_provider(
            "openai/" + policy.model,
            async_client=True,
            mode=Mode.JSON_SCHEMA if policy.structured_outputs else Mode.MD_JSON,
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            timeout=policy.timeout_seconds,
            max_retries=0,
        )

    async def complete[T: BaseModel](self, instruction: str, data: str, schema: type[T]) -> T:
        if not instruction.strip():
            raise ValueError("missing model instruction")
        if len(data) > 64000:
            raise ValueError("invalid model input")
        options: dict[str, Any] = {
            "max_completion_tokens": self.policy.max_completion_tokens,
            "timeout": self.policy.timeout_seconds,
        }
        for name in ("reasoning_effort", "temperature"):
            if (value := getattr(self.policy, name)) is not None:
                options[name] = value
        with _ProviderCall(self.policy.model, "structured_generation").observe() as call:
            async with asyncio.timeout(self.policy.timeout_seconds):
                try:
                    result = await self.client.create(
                        response_model=schema,
                        messages=[
                            {"role": "system", "content": instruction},
                            {"role": "user", "content": data},
                        ],
                        max_retries=_retrying(
                            self.policy, lambda error: not call.refused and retryable(error)
                        ),
                        **options,
                    )
                except InstructorError as error:
                    if call.refused:
                        raise RefusedOutputError("model refused the operation") from None
                    cause = (
                        error.__cause__ if isinstance(error, InstructorRetryException) else error
                    )
                    if isinstance(cause, (APIError, httpx.HTTPError)):
                        raise cause from None
                    raise ProviderOutputError("invalid structured model output") from error
                if call.refused:
                    raise RefusedOutputError("model refused the operation")
                return result


class DecisionLLM:
    def __init__(
        self,
        policy: VocabularyPolicy,
        *,
        api_key: str,
        endpoint: str,
        http_client: httpx.AsyncClient,
    ):
        self.policy = policy
        _instrument(http_client)
        self.client: AsyncDecisionsClient = instructor.from_provider(
            "openrouter/" + policy.decision_model,
            mode=Mode.DECISIONS,
            async_client=True,
            api_key=api_key,
            endpoint=endpoint,
            http_client=http_client,
            timeout=policy.timeout_seconds,
        )

    async def decide[T: BaseModel](self, schema: type[T], context: dict[str, Any]) -> T:
        with _ProviderCall(self.client.model, "decision").observe() as call:
            async with asyncio.timeout(self.policy.timeout_seconds):
                # Decisions has no native retry support; keep its request and parser native.
                async for attempt in _retrying(self.policy):
                    with attempt:
                        before = len(call.measurements)
                        try:
                            return await self.client.create(response_model=schema, context=context)
                        except ValueError as error:
                            if len(call.measurements) == before:
                                raise
                            raise ProviderOutputError("invalid decision model output") from error
        raise AssertionError("retry iterator completed without a result")
