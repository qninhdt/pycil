"""Bounded retries for provider transport and output validation."""

from json import JSONDecodeError

import httpx
from instructor.v2.core.errors import ResponseParsingError
from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    LengthFinishReasonError,
)
from pydantic import ValidationError

from pycil.utils.http import is_transient_http_status


class ProviderOutputError(Exception):
    pass


class RefusedOutputError(ProviderOutputError):
    pass


class ProviderTimeoutError(ProviderOutputError, TimeoutError):
    pass


def retryable(error: BaseException) -> bool:
    if isinstance(error, (RefusedOutputError, ProviderTimeoutError)):
        return False
    if isinstance(
        error,
        (
            ProviderOutputError,
            ValidationError,
            JSONDecodeError,
            APIConnectionError,
            APIResponseValidationError,
            LengthFinishReasonError,
            httpx.RequestError,
            ResponseParsingError,
        ),
    ):
        return True
    if isinstance(error, (APIStatusError, httpx.HTTPStatusError)):
        status = (
            getattr(error, "status_code", None)
            or getattr(getattr(error, "response", None), "status_code", None)
            or getattr(error, "status", None)
        )
        return is_transient_http_status(status)
    return False
