"""A client must be able to tell one conflict from another.

Every domain raise site in this codebase passes a snake_case identifier as its
only argument. If that identifier does not reach the wire as `code`, four
different session failures all arrive as `conflict`, and a client can see that
something conflicted but not whether to abandon the session, retry the same
question, or move on to a different one.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from pycil.platform.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    ServiceUnavailableError,
    TooManyRequestsError,
    UnauthorizedError,
    app_error_handler,
)


def _raise_through_handler(error: AppError) -> tuple[int, dict]:
    """Round-trip an error through the real handler rather than reading attributes.

    The attribute and the wire value are two different things, and only the
    second one a client can act on.
    """
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)

    @app.get("/boom")
    async def boom():
        raise error

    response = TestClient(app).get("/boom")
    return response.status_code, response.json()


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (ConflictError("session_scope_changed"), 409, "session_scope_changed"),
        (ConflictError("question_not_assessable"), 409, "question_not_assessable"),
        (ConflictError("question_not_issued_for_session"), 409, "question_not_issued_for_session"),
        (ConflictError("question_not_available"), 409, "question_not_available"),
        (NotFoundError("session_not_found"), 404, "session_not_found"),
        (NotFoundError("sense_not_found"), 404, "sense_not_found"),
        (
            ServiceUnavailableError("question_preparation_exhausted"),
            503,
            "question_preparation_exhausted",
        ),
        (UnauthorizedError("invalid_refresh_token"), 401, "invalid_refresh_token"),
        (ForbiddenError("assistant_actor_revoked"), 403, "assistant_actor_revoked"),
        (PayloadTooLargeError("assistant_message_too_long"), 413, "assistant_message_too_long"),
    ],
)
def test_identifier_message_reaches_the_wire_as_the_code(error, expected_status, expected_code):
    status_code, body = _raise_through_handler(error)
    assert status_code == expected_status
    assert body["code"] == expected_code


def test_the_four_session_conflicts_are_distinguishable():
    """All four are 409. The status alone cannot drive a recovery decision."""
    codes = {
        _raise_through_handler(ConflictError(identifier))[1]["code"]
        for identifier in (
            "session_scope_changed",
            "question_not_assessable",
            "question_not_issued_for_session",
            "question_not_available",
        )
    }
    assert len(codes) == 4


@pytest.mark.parametrize(
    "prose",
    [
        "Too many requests",
        "oauth_exchange_failed: connection reset",
        "Body too large",
        "refresh_token_pepper is not configured",
    ],
)
def test_prose_is_not_promoted_to_a_code(prose):
    """A sentence is not an identifier, and must not be offered as one to branch on."""
    _, body = _raise_through_handler(ConflictError(prose))
    assert body["code"] == "conflict"
    assert body["detail"] == prose


def test_explicit_code_wins_over_the_message():
    _, body = _raise_through_handler(ForbiddenError("not_node_owner", code="forbidden"))
    assert body["code"] == "forbidden"
    assert body["detail"] == "not_node_owner"


def test_default_message_keeps_the_class_code():
    status_code, body = _raise_through_handler(TooManyRequestsError(retry_after=30))
    assert status_code == 429
    assert body["code"] == "too_many_requests"
