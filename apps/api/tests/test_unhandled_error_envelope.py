"""An unexpected exception must still leave through the canonical error envelope.

`create_app` registers handlers for `AppError`, `RequestValidationError` and
`HTTPException`. Anything else — a `KeyError` from a malformed payload, a
`RecursionError`, a driver raising something undeclared — falls through to
Starlette's default, which returns a bare `Internal Server Error` with no code, no
`requestId`, and a content type the client's error parser does not expect.

That matters beyond tidiness. The web client branches on `error.code`
(`lib/api/error-codes.generated.ts` keys `ERROR_TAXONOMY` off it), so an
un-enveloped 500 is not merely ugly — it is unparseable, and the browser reports
it as a network-shaped failure rather than a server error. Correlating it with a
log line is also impossible without the request id.

The handler deliberately does NOT leak the exception message. An unexpected error
carries whatever the raising library chose to put in it, which can include a
connection string or a row of user data.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from pycil.common.errors import unhandled_error_handler
from pycil.common.middleware import install_middleware
from pycil.main import create_app


def _app_that_raises(exc: Exception, *, with_middleware: bool = False) -> FastAPI:
    """A minimal app wired exactly like production's catch-all.

    `with_middleware` adds the real middleware stack, which is what populates
    `request.state.request_id`. Off by default so the handler is tested in
    isolation; on for the test that asserts the id reaches the envelope.
    """
    app = FastAPI()
    if with_middleware:
        install_middleware(app)
    app.add_exception_handler(Exception, unhandled_error_handler)

    @app.get("/boom")
    async def boom():
        raise exc

    return app


@pytest.mark.parametrize(
    "exc",
    [
        KeyError("question_pool"),
        RecursionError("maximum recursion depth exceeded"),
        ValueError("some driver detail"),
        TypeError("unexpected keyword argument"),
    ],
)
def test_an_unexpected_exception_returns_the_error_envelope(exc):
    client = TestClient(_app_that_raises(exc), raise_server_exceptions=False)

    response = client.get("/boom", headers={"X-Request-ID": "r-boom"})

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    # The shape the client parses, in full — a missing key here is a client crash.
    assert set(body["error"]) == {"code", "message", "details", "requestId"}


def test_the_envelope_does_not_leak_the_exception_message():
    """An unexpected exception's text is not a message we chose to publish."""
    secret = "postgresql://pycil:hunter2@db:5432/pycil"
    client = TestClient(_app_that_raises(RuntimeError(secret)), raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 500
    assert secret not in response.text
    assert "hunter2" not in response.text


def test_the_request_id_survives_into_the_envelope():
    """Without it, a 500 cannot be matched to the log line that explains it."""
    app = _app_that_raises(KeyError("k"), with_middleware=True)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom", headers={"X-Request-ID": "trace-me"})

    assert response.json()["error"]["requestId"] == "trace-me"


def test_the_real_app_registers_a_catch_all():
    """Guard the wiring, not just the handler: an unregistered handler is a bare 500."""
    app = create_app()
    assert Exception in app.exception_handlers, (
        "create_app must register a catch-all so an unexpected type still "
        "returns ErrorEnvelope"
    )
