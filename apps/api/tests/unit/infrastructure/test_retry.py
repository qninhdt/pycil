import httpx
import pytest
from instructor.v2.core.errors import IncompleteOutputException, ResponseParsingError

from pycil.infrastructure.retry import ProviderOutputError, RefusedOutputError, retryable


@pytest.mark.parametrize(
    "status, expected",
    [(401, False), (422, False), (408, True), (409, True), (429, True), (503, True)],
)
def test_provider_status_policy(status, expected):
    request = httpx.Request("POST", "https://provider.test")
    error = httpx.HTTPStatusError(
        "provider status", request=request, response=httpx.Response(status, request=request)
    )
    assert retryable(error) is expected


@pytest.mark.parametrize(
    "error, expected",
    [
        (ProviderOutputError("invalid output"), True),
        (RefusedOutputError("refused"), False),
        (ResponseParsingError("invalid structured response"), True),
        (IncompleteOutputException(), False),
        (httpx.ConnectError("disconnected"), True),
        (ValueError("invalid local configuration"), False),
    ],
)
def test_output_and_connection_retry_policy(error, expected):
    assert retryable(error) is expected
