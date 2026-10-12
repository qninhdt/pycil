import io
import json
import logging

from pycil.logging import (
    bind_contextvars,
    clear_contextvars,
    configure_logging,
    get_logger,
    unbind_contextvars,
)


def test_json_logging_output():
    configure_logging(log_format="json", log_level="INFO")
    logger = get_logger("test.pycil")

    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    formatter = root_logger.handlers[0].formatter

    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(formatter)
    root_logger.handlers = [test_handler]

    try:
        clear_contextvars()
        bind_contextvars(request_id="req-test-uuid")
        logger.info("user_authenticated", user_id="u123")

        output = stream.getvalue().strip()
        data = json.loads(output)

        assert data["event"] == "user_authenticated"
        assert data["user_id"] == "u123"
        assert data["request_id"] == "req-test-uuid"
        assert data["logger"] == "test.pycil"
        assert data["level"] == "info"
        assert "timestamp" in data
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


def test_stdlib_logging_integration():
    configure_logging(log_format="json", log_level="INFO")

    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    formatter = root_logger.handlers[0].formatter

    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(formatter)
    root_logger.handlers = [test_handler]

    try:
        clear_contextvars()
        bind_contextvars(request_id="req-stdlib")
        std_logger = logging.getLogger("pycil.external_lib")
        std_logger.warning("something_warned %s", "detail", extra={"extra_field": "val123"})

        output = stream.getvalue().strip()
        data = json.loads(output)

        assert "something_warned detail" in data["event"]
        assert data["extra_field"] == "val123"
        assert data["request_id"] == "req-stdlib"
        assert data["logger"] == "pycil.external_lib"
        assert data["level"] == "warning"
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


def test_contextvars_management():
    clear_contextvars()
    bind_contextvars(a="1", b="2")
    unbind_contextvars("a")
    # Verify via structlog logger
    configure_logging(log_format="json", log_level="INFO")

    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    try:
        logger = get_logger("test.context")
        logger.info("checked")
        data = json.loads(stream.getvalue().strip())
        assert "a" not in data
        assert data["b"] == "2"

        clear_contextvars()
        stream.seek(0)
        stream.truncate(0)
        logger.info("cleared")
        data2 = json.loads(stream.getvalue().strip())
        assert "b" not in data2
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


def test_uvicorn_loggers_routed_to_root():
    configure_logging(log_format="json", log_level="INFO")
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        uv_log = logging.getLogger(name)
        assert len(uv_log.handlers) == 0
        assert uv_log.propagate is True
        assert uv_log.level == logging.NOTSET


def test_console_logging_configuration():
    configure_logging(log_format="console", log_level="DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    # restore standard configuration
    configure_logging()


async def test_request_boundary_binds_contextvars():
    import structlog

    from pycil.http import RequestBoundary

    captured_context = {}

    async def inner_app(scope, receive, send):
        captured_context.update(structlog.contextvars.get_contextvars())
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})

    boundary = RequestBoundary(inner_app)
    sent_messages = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent_messages.append(message)

    await boundary(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/test-ctx",
            "headers": [(b"x-request-id", b"0192e2c0-8a70-7111-9a00-111111111111")],
        },
        receive,
        send,
    )

    assert captured_context["request_id"] == "0192e2c0-8a70-7111-9a00-111111111111"
    assert captured_context["method"] == "POST"
    assert captured_context["path"] == "/api/v1/test-ctx"
    # Ensure finally: clear_contextvars() cleaned up contextvars on request completion
    assert structlog.contextvars.get_contextvars() == {}


async def test_actor_binds_actor_id_on_cache_hit():
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    import structlog
    from fastapi.security import HTTPAuthorizationCredentials

    from pycil.account.auth import ActorContext, actor
    from pycil.account.plans import Plan

    clear_contextvars()
    user_id = uuid4()
    context = ActorContext(
        id=user_id,
        clerk_subject="sub_123",
        display_name="Learner",
        handle="learner",
        plan=Plan.FREE,
        settings={},
        cycle_anchor=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    mock_cache = AsyncMock()
    mock_cache.get.return_value = context

    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer valid"
    mock_request.app.state.identity.subject = AsyncMock(return_value="sub_123")

    mock_session = MagicMock()
    mock_session.info = {"cache": mock_cache}

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid")

    result = await actor(mock_request, mock_session, credentials)
    assert result == context
    assert structlog.contextvars.get_contextvars().get("actor_id") == str(user_id)
    clear_contextvars()


async def test_request_boundary_structured_error_log():
    from pycil.http import RequestBoundary

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    async def failing_app(scope, receive, send):
        raise RuntimeError("database connection failed with secret credentials")

    boundary = RequestBoundary(failing_app)
    sent_messages = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent_messages.append(message)

    try:
        await boundary(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/failing",
                "headers": [],
            },
            receive,
            send,
        )

        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        assert len(lines) == 2
        data = lines[0]

        assert data["event"] == "request_failed"
        assert data["level"] == "error"
        assert data["logger"] == "pycil.http"
        assert data["method"] == "GET"
        assert data["path"] == "/api/v1/failing"
        assert "request_id" in data
        assert "secret credentials" not in stream.getvalue()

        completed_data = lines[1]
        assert completed_data["event"] == "http_request_completed"
        assert completed_data["status_code"] == 500
        assert "duration_ms" in completed_data
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_cache_structured_warning_log():
    from unittest.mock import AsyncMock

    from pydantic import BaseModel
    from redis.exceptions import ConnectionError

    from pycil.cache import RedisCache

    class MockPolicy:
        actor_ttl_seconds = 60
        max_entries = 100
        max_value_bytes = 1024

    class Model(BaseModel):
        val: str

    mock_redis = AsyncMock()
    mock_redis.get.side_effect = ConnectionError("Redis connection lost")

    cache = RedisCache(mock_redis, "test_ns", MockPolicy())

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    try:
        clear_contextvars()
        bind_contextvars(request_id="req-cache-test")
        result = await cache.get("sample_key", Model)
        assert result is None

        output = stream.getvalue().strip()
        data = json.loads(output)

        assert data["event"] == "cache_read_failed"
        assert data["level"] == "warning"
        assert data["cache_key"] == "sample_key"
        assert data["request_id"] == "req-cache-test"
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_generation_structured_exception_log():
    from unittest.mock import AsyncMock

    from pycil.vocabulary.generation import Generations

    class MockGenConfig:
        generation = type("Gen", (), {"timeout_seconds": 10, "examples_per_sense": 2})()

    mock_lexicon = AsyncMock()
    mock_lexicon.generate_word.side_effect = RuntimeError("LLM synthesis model exploded")

    gen = Generations(mock_lexicon, MockGenConfig())
    result = {"task_id": "gen-task-456", "status": "RUNNING"}

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    try:
        clear_contextvars()
        bind_contextvars(request_id="req-gen-test")
        await gen._run("word:test", None, "test", result)

        assert result["status"] == "FAILED"
        assert result["error"] == "generation_failed"

        output = stream.getvalue().strip()
        data = json.loads(output)

        assert data["event"] == "word_generation_failed"
        assert data["level"] == "error"
        assert data["task_id"] == "gen-task-456"
        assert data["target"] == "test"
        assert data["key"] == "word:test"
        assert data["request_id"] == "req-gen-test"
        assert "LLM synthesis model exploded" in data["exception"]
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_conversation_lease_release_structured_exception_log():
    from unittest.mock import AsyncMock, MagicMock

    import pytest
    from redis.exceptions import ConnectionError

    from pycil.assistant.conversations import guard
    from pycil.http import Problem

    mock_redis = MagicMock()
    mock_lock = AsyncMock()
    mock_lock.acquire.return_value = True
    mock_lock.release.side_effect = ConnectionError("Redis down on release")
    mock_redis.lock.return_value = mock_lock

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    try:
        clear_contextvars()
        bind_contextvars(request_id="req-conv-test")

        with pytest.raises(Problem) as exc_info:
            async with guard(mock_redis, "conv-999"):
                pass
        assert exc_info.value.status == 503

        output = stream.getvalue().strip()
        data = json.loads(output)

        assert data["event"] == "conversation_lease_release_failed"
        assert data["level"] == "error"
        assert data["conversation_id"] == "conv-999"
        assert data["request_id"] == "req-conv-test"
        assert "Redis down on release" in data["exception"]
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_http_request_completed_success_log():
    from pycil.http import RequestBoundary

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    async def ok_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    boundary = RequestBoundary(ok_app)

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        pass

    try:
        clear_contextvars()
        await boundary(
            {"type": "http", "method": "GET", "path": "/api/v1/ping", "headers": []},
            receive,
            send,
        )
        output = stream.getvalue().strip()
        data = json.loads(output)
        assert data["event"] == "http_request_completed"
        assert data["status_code"] == 200
        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], float)
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_body_limit_structured_logs():
    from types import SimpleNamespace

    from pycil.http import BodyLimit

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    async def inner_app(scope, receive, send):
        pass

    limit = BodyLimit(inner_app)
    mock_app = SimpleNamespace(
        state=SimpleNamespace(product=SimpleNamespace(http=SimpleNamespace(max_body_bytes=10)))
    )

    try:
        clear_contextvars()
        # Header limit exceeded
        sent = []

        async def async_send(msg):
            sent.append(msg)

        await limit(
            {
                "type": "http",
                "method": "POST",
                "path": "/upload",
                "headers": [(b"content-length", b"50")],
                "app": mock_app,
            },
            None,
            async_send,
        )
        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "http_body_limit_exceeded"
        assert line["phase"] == "header"
        assert line["max_bytes"] == 10
        assert line["content_length"] == 50

        # Invalid content length
        await limit(
            {
                "type": "http",
                "method": "POST",
                "path": "/upload",
                "headers": [(b"content-length", b"invalid")],
                "app": mock_app,
            },
            None,
            async_send,
        )
        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "http_invalid_content_length"
        assert line["content_length_raw"] == "invalid"

        # Stream limit exceeded
        chunks = [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"789012", "more_body": False},
        ]

        async def chunk_recv():
            return chunks.pop(0)

        await limit(
            {
                "type": "http",
                "method": "POST",
                "path": "/upload",
                "headers": [],
                "app": mock_app,
            },
            chunk_recv,
            async_send,
        )
        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "http_body_limit_exceeded"
        assert line["phase"] == "stream"
        assert line["max_bytes"] == 10
        assert line["content_length"] == 12
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_validation_response_structured_log():
    from unittest.mock import MagicMock

    from fastapi.exceptions import RequestValidationError

    from pycil.http import validation_response

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    mock_error = MagicMock(spec=RequestValidationError)
    mock_error.errors.return_value = [
        {"loc": ("body", "email"), "input": "secret-pwd@test.com", "msg": "invalid"}
    ]

    try:
        clear_contextvars()
        response = await validation_response(MagicMock(), mock_error)
        assert response.status_code == 422
        output = stream.getvalue().strip()
        data = json.loads(output)
        assert data["event"] == "http_validation_failed"
        assert data["fields"] == [["body", "email"]]
        assert "secret-pwd" not in output
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_readiness_check_failed_logging():
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    from pycil.http import Problem
    from pycil.main import create_app

    app = create_app()

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    # Ready route with DB failure
    app.state.engine = MagicMock()
    app.state.engine.connect.side_effect = RuntimeError("DB down")

    ready_handler = next(
        route.endpoint for route in app.routes if getattr(route, "path", None) == "/ready"
    )

    try:
        clear_contextvars()
        with pytest.raises(Problem):
            await ready_handler()
        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "readiness_check_failed"
        assert line["component"] == "database"
        assert line["error_type"] == "RuntimeError"

        # Ready route with Redis failure
        mock_conn = MagicMock()
        mock_conn.__aenter__ = AsyncMock()
        mock_conn.__aexit__ = AsyncMock()
        app.state.engine.connect = MagicMock(return_value=mock_conn)
        app.state.redis = MagicMock()
        app.state.redis.ping = AsyncMock(side_effect=ConnectionError("Redis down"))

        with pytest.raises(Problem):
            await ready_handler()
        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "readiness_check_failed"
        assert line["component"] == "redis"
        assert line["error_type"] == "ConnectionError"
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_database_query_timeout_logging():
    from unittest.mock import MagicMock

    import pytest
    from sqlalchemy.exc import DBAPIError

    from pycil.dependencies import session
    from pycil.http import Problem

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    mock_request = MagicMock()
    mock_orig = MagicMock()
    mock_orig.sqlstate = "57014"
    mock_dbapi_error = DBAPIError("SELECT 1", {}, mock_orig)

    class FailingSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_request.app.state.sessions.return_value = FailingSession()

    try:
        clear_contextvars()
        gen = session(mock_request)
        await anext(gen)
        with pytest.raises(Problem) as exc:
            await gen.athrow(mock_dbapi_error)
        assert exc.value.status == 503

        data = json.loads(stream.getvalue().strip())
        assert data["event"] == "database_query_timeout"
        assert data["sqlstate"] == "57014"
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_auth_identity_failure_logging():
    from unittest.mock import MagicMock, patch

    import jwt
    import pytest

    from pycil.account.auth import Identity
    from pycil.http import Problem

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    deployment = MagicMock()
    deployment.clerk_jwks_url = "https://clerk.invalid/.well-known/jwks.json"
    identity = Identity(deployment)

    try:
        clear_contextvars()
        with patch.object(
            identity.keys, "get_signing_key_from_jwt", side_effect=jwt.InvalidTokenError("invalid")
        ):
            with pytest.raises(Problem) as exc:
                await identity.subject("sensitive-raw-token")
            assert exc.value.status == 401

        data = json.loads(stream.getvalue().strip())
        assert data["event"] == "auth_token_verification_failed"
        assert data["error_type"] == "InvalidTokenError"
        assert "sensitive-raw-token" not in stream.getvalue()
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_clerk_lifecycle_logging():
    from unittest.mock import AsyncMock, MagicMock

    import pytest

    from pycil.account.lifecycle import clerk_user
    from pycil.http import Problem

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    mock_http = MagicMock()
    mock_deployment = MagicMock()
    mock_deployment.clerk_secret_key.get_secret_value.return_value = "secret_key_123"

    try:
        clear_contextvars()
        # 404 not found
        res_404 = MagicMock(status_code=404, is_success=False)
        mock_http.request = AsyncMock(return_value=res_404)
        with pytest.raises(Problem):
            await clerk_user(mock_http, mock_deployment, "user_404")

        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "clerk_user_not_found"
        assert line["subject"] == "user_404"
        assert "secret_key_123" not in stream.getvalue()

        # 500 error
        res_500 = MagicMock(status_code=500, is_success=False)
        mock_http.request = AsyncMock(return_value=res_500)
        with pytest.raises(Problem):
            await clerk_user(mock_http, mock_deployment, "user_500")

        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "clerk_api_request_failed"
        assert line["status_code"] == 500
        assert "secret_key_123" not in stream.getvalue()
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_usage_structured_logs():
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    import pytest

    from pycil.account.models import User
    from pycil.account.plans import Feature, Plan
    from pycil.account.usage import admit, settle
    from pycil.http import Problem

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    uid = uuid4()
    mock_user = MagicMock(spec=User)
    mock_user.id = uid
    mock_user.plan = Plan.FREE
    mock_user.cycle_anchor = datetime.now(UTC)

    mock_session = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock()
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.scalar = AsyncMock(return_value=mock_user)

    mock_config = MagicMock()
    mock_config.plans = {Plan.FREE: MagicMock(features=set(), monthly_allowance_units=10)}

    try:
        clear_contextvars()
        with pytest.raises(Problem) as exc:
            await admit(mock_session, uid, mock_config, Feature.ADVANCED_GRADING, datetime.now(UTC))
        assert exc.value.status == 403

        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "feature_access_denied"
        assert line["user_id"] == str(uid)
        assert line["feature"] == Feature.ADVANCED_GRADING.value

        # Settle conflict test
        mock_event = MagicMock()
        mock_event.period_id = uuid4()
        mock_event.feature = Feature.ASSISTANT
        mock_event.units = 5
        mock_event.unmetered_calls = 0

        mock_period = MagicMock()
        mock_period.user_id = uid

        mock_session.execute = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_period)
        mock_session.scalar = AsyncMock(side_effect=[mock_user, mock_event])

        exec_key = uuid4()
        with pytest.raises(Problem) as exc_conflict:
            await settle(
                mock_session,
                uid,
                mock_config,
                execution_key=exec_key,
                feature=Feature.ASSISTANT,
                units=10,  # mismatch with 5
                unmetered_calls=0,
                moment=datetime.now(UTC),
            )
        assert exc_conflict.value.status == 409

        line = json.loads(stream.getvalue().strip().splitlines()[-1])
        assert line["event"] == "quota_settle_conflict"
        assert line["user_id"] == str(uid)
        assert line["execution_key"] == str(exec_key)
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_schema_verification_structured_logs():
    from unittest.mock import MagicMock

    import pytest

    from pycil.database import verify_schema

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    mock_engine = MagicMock()
    mock_engine.connect.side_effect = RuntimeError("DB connection error")

    try:
        clear_contextvars()
        with pytest.raises(RuntimeError):
            await verify_schema(mock_engine)

        data = json.loads(stream.getvalue().strip())
        assert data["event"] == "schema_verification_failed"
        assert data["level"] == "error"
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_account_handle_conflict_logging():
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    import pytest
    from sqlalchemy.exc import IntegrityError

    from pycil.account.api import edit_profile
    from pycil.account.models import User
    from pycil.account.schemas import ProfilePatch
    from pycil.http import Problem

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    mock_actor = MagicMock(id=uuid4())
    mock_user = MagicMock(spec=User, id=mock_actor.id)

    mock_session = MagicMock()
    mock_session.info = {}
    mock_session.begin.return_value.__aenter__ = AsyncMock()
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.scalar = AsyncMock(return_value=mock_user)

    mock_orig = MagicMock()
    mock_orig.sqlstate = "23505"
    mock_session.flush = AsyncMock(side_effect=IntegrityError("unique violation", {}, mock_orig))

    patch_data = ProfilePatch(handle="taken_handle")

    try:
        clear_contextvars()
        with pytest.raises(Problem) as exc:
            await edit_profile(patch_data, mock_actor, MagicMock(), mock_session)
        assert exc.value.status == 409

        data = json.loads(stream.getvalue().strip())
        assert data["event"] == "account_handle_conflict"
        assert data["handle"] == "taken_handle"
        assert data["level"] == "warning"
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_generation_lifecycle_structured_logging():
    import asyncio
    from unittest.mock import AsyncMock
    from uuid import uuid7

    import pytest

    from pycil.vocabulary.generation import Generations

    class MockGenConfig:
        generation = type("Gen", (), {"timeout_seconds": 10, "examples_per_sense": 2})()

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    try:
        clear_contextvars()
        # 1. Success case: word_generation_started and word_generation_completed
        mock_word = type("Word", (), {"id": 101, "senses": [1, 2]})()
        mock_lexicon = AsyncMock()
        mock_lexicon.generate_word.return_value = mock_word

        gen = Generations(mock_lexicon, MockGenConfig())
        res = await gen.submit("apple")
        assert res["status"] == "RUNNING"
        await gen.wait([res["task_id"]])

        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        events = {entry["event"]: entry for entry in lines}
        assert "word_generation_started" in events
        assert events["word_generation_started"]["target"] == "apple"
        assert "word_generation_completed" in events
        assert events["word_generation_completed"]["word_id"] == 101
        assert events["word_generation_completed"]["sense_count"] == 2

        # 2. Deduplication: word_generation_deduplicated
        slow_future = asyncio.Future()
        mock_lexicon.generate_word.side_effect = lambda *args, **kwargs: slow_future
        res2 = await gen.submit("banana")
        res2_dup = await gen.submit("banana")
        assert res2["task_id"] == res2_dup["task_id"]

        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        dup_events = [entry for entry in lines if entry["event"] == "word_generation_deduplicated"]
        assert len(dup_events) == 1
        assert dup_events[0]["target"] == "banana"

        slow_future.cancel()
        await gen.close()

        # 3. Timeout: word_generation_timed_out
        stream.seek(0)
        stream.truncate(0)
        gen3 = Generations(mock_lexicon, MockGenConfig())
        result3 = {"task_id": uuid7(), "status": "RUNNING"}
        mock_lexicon.generate_word.side_effect = TimeoutError("timed out")
        await gen3._run("word:orange", None, "orange", result3)
        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        assert any(entry["event"] == "word_generation_timed_out" for entry in lines)

        # 4. Cancelled: word_generation_cancelled
        stream.seek(0)
        stream.truncate(0)
        result4 = {"task_id": uuid7(), "status": "RUNNING"}
        mock_lexicon.generate_word.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await gen3._run("word:grape", None, "grape", result4)
        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        assert any(entry["event"] == "word_generation_cancelled" for entry in lines)
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_library_scope_bounded_logging():
    from time import monotonic
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    import pytest
    from sqlalchemy.exc import DBAPIError

    from pycil.http import Problem
    from pycil.library.scope import ScopeBudget, bounded

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    viewer_id = uuid4()
    mock_config = MagicMock()
    mock_config.library.scope_timeout_seconds = 10.0
    mock_config.library.statement_timeout_ms = 5000

    try:
        clear_contextvars()
        # 1. Budget exhausted
        exhausted_budget = ScopeBudget(viewer_id=viewer_id, started_at=monotonic() - 20.0)
        mock_session = AsyncMock()
        with pytest.raises(Problem) as exc:
            async with bounded(mock_session, mock_config, exhausted_budget):
                pass
        assert exc.value.status == 503
        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        assert any(
            entry["event"] == "library_scope_budget_exhausted"
            and entry["viewer_id"] == str(viewer_id)
            for entry in lines
        )

        # 2. Scope timeout (TimeoutError)
        stream.seek(0)
        stream.truncate(0)
        valid_budget = ScopeBudget(viewer_id=viewer_id, started_at=monotonic())
        with pytest.raises(Problem) as exc:
            async with bounded(mock_session, mock_config, valid_budget):
                raise TimeoutError("timeout")
        assert exc.value.status == 503
        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        assert any(
            entry["event"] == "library_scope_timeout" and entry["viewer_id"] == str(viewer_id)
            for entry in lines
        )

        # 3. Statement timeout (DBAPIError 57014)
        stream.seek(0)
        stream.truncate(0)
        mock_orig = MagicMock()
        mock_orig.sqlstate = "57014"
        stmt_error = DBAPIError("statement timeout", {}, mock_orig)
        with pytest.raises(Problem) as exc:
            async with bounded(mock_session, mock_config, valid_budget):
                raise stmt_error
        assert exc.value.status == 503
        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        assert any(
            entry["event"] == "library_statement_timeout" and entry["viewer_id"] == str(viewer_id)
            for entry in lines
        )
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_study_preparation_structured_logging():
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    import pytest
    from lexi_ai.errors import QuestionArtifactBankChangedError

    from pycil.http import Problem
    from pycil.study.preparation import prepare

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    user_id = uuid4()
    node_id = uuid4()
    mock_user = MagicMock(id=user_id)
    mock_db_user = MagicMock(id=user_id, plan="FREE", settings={})

    mock_config = MagicMock()
    mock_config.learning.validate_preferences.return_value = None
    mock_config.generation.question_artifact_batch_size = 10
    mock_config.generation.correct_count = 1
    mock_config.generation.distractor_count = 3

    mock_session = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock()
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_session.connection = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=mock_db_user)
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    mock_prefs = MagicMock(
        max_sense_count=5,
        questions_per_sense=2,
        question_types=["WORD_TO_DEFINITION"],
        formats=["SINGLE_CHOICE"],
    )
    mock_prefs.model_copy.return_value = mock_prefs

    try:
        clear_contextvars()
        mock_lexicon = AsyncMock()
        from sqlalchemy import literal, select

        with (
            patch("pycil.study.preparation.effective_learning", return_value=mock_prefs),
            patch("pycil.study.preparation.readable", AsyncMock()),
            patch(
                "pycil.study.preparation.member_ids",
                AsyncMock(return_value=select(literal(1).label("sense_id"))),
            ),
        ):
            res = await prepare(mock_session, mock_lexicon, mock_user, node_id, mock_config)
            assert res["actual_sense_count"] == 0
            lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
            events = {entry["event"]: entry for entry in lines}
            assert "study_preparation_started" in events
            assert events["study_preparation_started"]["user_id"] == str(user_id)
            assert events["study_preparation_started"]["node_id"] == str(node_id)
            assert "study_preparation_completed" in events
            assert events["study_preparation_completed"]["sense_count"] == 0

            # Artifact failure
            stream.seek(0)
            stream.truncate(0)
            mock_row = MagicMock(sense_id=1, elo=1500.0, reason="NEW")
            mock_session.execute = AsyncMock(
                return_value=MagicMock(all=MagicMock(return_value=[mock_row]))
            )
            mock_config.learning.mastery.level.return_value = 1
            mock_config.learning.pair_levels = {"WORD_TO_DEFINITION": {"SINGLE_CHOICE": 1}}
            mock_lexicon.retrieve_question_artifacts.side_effect = (
                QuestionArtifactBankChangedError()
            )

            with pytest.raises(Problem) as exc:
                await prepare(mock_session, mock_lexicon, mock_user, node_id, mock_config)
            assert exc.value.status == 409
            lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
            assert any(
                entry["event"] == "study_artifact_retrieval_failed"
                and entry["error_type"] == "QuestionArtifactBankChangedError"
                for entry in lines
            )
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_study_reviews_structured_logging():
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    import pytest
    from lexi_ai import QUESTION_ARTIFACT_MAP

    from pycil.http import Problem
    from pycil.study.reviews import request_hash, review
    from pycil.study.schemas import Review, ReviewBatch

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    user_id = uuid4()
    event_key = uuid4()
    mock_config = MagicMock()
    mock_config.learning.limits.max_review_batch = 100
    mock_config.learning.pair_levels = {"WORD_TO_DEFINITION": {"SINGLE_CHOICE": 1}}
    mock_config.learning.mastery = type(
        "M",
        (),
        {
            "policy_version": 1,
            "opponent_elo": [1500.0],
            "initial_elo": 1500.0,
            "k_elo": 32.0,
            "horizon_hours": 24.0,
            "level": lambda self, elo: 1,
        },
    )()
    mock_config.learning.fsrs = type(
        "F",
        (),
        {
            "initial_stability": 2.0,
            "initial_difficulty": 5.0,
            "desired_retention": 0.9,
            "max_interval_days": 365,
        },
    )()

    review_item = Review(
        question_artifact_id=1,
        question_type="WORD_TO_DEFINITION",
        format="SINGLE_CHOICE",
        diagnostics={"correct": True},
        answered_at=datetime.now(UTC),
    )
    data = ReviewBatch(results=[review_item])

    mock_session = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock()
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = AsyncMock()
    mock_session.scalars = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.scalar = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()

    try:
        clear_contextvars()
        with (
            patch("pycil.study.reviews.transaction_lock", AsyncMock()),
            patch("pycil.study.reviews.require_user", AsyncMock()),
            patch("pycil.study.reviews.preferences", return_value=MagicMock(timezone="UTC")),
        ):
            # 1. Replay hit
            mock_receipt = MagicMock(
                request_hash=request_hash(data),
                result={"status": "replayed"},
            )
            mock_session.get.return_value = mock_receipt

            res = await review(mock_session, user_id, data, event_key, mock_config)
            assert res == {"status": "replayed"}
            lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
            assert any(
                entry["event"] == "review_batch_replayed" and entry["event_key"] == str(event_key)
                for entry in lines
            )

            # 2. Conflict
            stream.seek(0)
            stream.truncate(0)
            mock_receipt.request_hash = "mismatched_hash"
            with pytest.raises(Problem) as exc:
                await review(mock_session, user_id, data, event_key, mock_config)
            assert exc.value.status == 409
            lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
            assert any(
                entry["event"] == "review_batch_conflict" and entry["event_key"] == str(event_key)
                for entry in lines
            )

            # 3. Successful review batch completed with elo and fsrs updates
            stream.seek(0)
            stream.truncate(0)
            mock_session.get.return_value = None
            mock_artifact = MagicMock(
                id=1,
                artifact_type=QUESTION_ARTIFACT_MAP[review_item.question_type],
                sense_id=10,
            )
            mock_session.scalars.side_effect = [
                MagicMock(all=MagicMock(return_value=[mock_artifact])),  # artifacts
                MagicMock(all=MagicMock(return_value=[])),  # memories
            ]
            mock_session.execute.side_effect = [
                MagicMock(all=MagicMock(return_value=[(10, 100)])),  # words
                None,  # insert UserSense
                None,  # insert DailyActivity
            ]
            mock_session.scalar.return_value = {}  # User.settings

            res = await review(mock_session, user_id, data, event_key, mock_config)
            lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
            events = {entry["event"]: entry for entry in lines}
            assert "study_elo_updated" in events
            assert events["study_elo_updated"]["sense_id"] == 10
            assert "study_fsrs_transitioned" in events
            assert events["study_fsrs_transitioned"]["sense_id"] == 10
            assert "review_batch_completed" in events
            assert events["review_batch_completed"]["total_reviews"] == 1
            assert events["review_batch_completed"]["applied_count"] == 1
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_study_grading_failed_structured_logging():
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    import pytest
    from lexi_ai.errors import LexiconError

    from pycil.account.plans import Feature, Plan
    from pycil.http import Problem
    from pycil.study.api import grade
    from pycil.study.schemas import Grade

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    user_id = uuid4()
    mock_actor = MagicMock(id=user_id)
    mock_config = MagicMock()
    mock_config.plans = {Plan.PRO: MagicMock(features=[Feature.ADVANCED_GRADING])}
    mock_config.learning.limits.max_answer_chars = 1000

    mock_session = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock()
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_session.scalar = AsyncMock(return_value=Plan.PRO)

    mock_lexicon = AsyncMock()
    mock_lexicon.grade_answer.side_effect = LexiconError("LLM grading timeout")

    data = Grade(
        question_artifact_id=999,
        question_type="WORD_TO_DEFINITION",
        format="SHORT_ANSWER",
        answer="my answer",
    )

    try:
        clear_contextvars()
        with pytest.raises(Problem) as exc:
            await grade(data, mock_actor, mock_config, mock_lexicon, mock_session)
        assert exc.value.status == 503
        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        assert any(
            entry["event"] == "study_grading_failed"
            and entry["user_id"] == str(user_id)
            and entry["question_artifact_id"] == 999
            for entry in lines
        )
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()


async def test_library_nodes_structured_logging():
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    from pycil.library.models import NodeRole, NodeSpace, NodeType
    from pycil.library.nodes import (
        create_node,
        delete_node,
        move_node,
        replace_membership,
    )
    from pycil.library.schemas import NodeCreate, NodeMove

    configure_logging(log_format="json", log_level="INFO")
    stream = io.StringIO()
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    test_handler = logging.StreamHandler(stream)
    test_handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.handlers = [test_handler]

    owner_id = uuid4()
    parent_id = uuid4()
    node_id = uuid4()
    mock_config = MagicMock()
    mock_config.library.max_owned_nodes = 100
    mock_config.library.max_senses_per_deck = 50
    mock_config.library.max_owned_memberships = 500

    mock_session = MagicMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock()
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.scalars = AsyncMock()
    mock_session.execute = AsyncMock()

    try:
        clear_contextvars()
        # 1. create_node
        with (
            patch("pycil.library.nodes.lock_owner", AsyncMock()),
            patch("pycil.library.nodes.check_node_quota", AsyncMock(return_value=0)),
            patch("pycil.library.nodes.default_parent", AsyncMock(return_value=parent_id)),
            patch(
                "pycil.library.nodes.validate_parent",
                AsyncMock(return_value=MagicMock(space=NodeSpace.PERSONAL)),
            ),
            patch("pycil.library.nodes.validate_publication", AsyncMock()),
            patch("pycil.library.nodes.add_paths", AsyncMock()),
            patch("pycil.library.nodes.row_data", lambda n: {"id": node_id}),
        ):
            data = NodeCreate(name="My Folder", type="FOLDER", parent_id=parent_id)
            await create_node(mock_session, owner_id, data, mock_config)

        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        created_events = [entry for entry in lines if entry["event"] == "library_node_created"]
        assert len(created_events) == 1
        assert created_events[0]["name"] == "My Folder"
        assert created_events[0]["owner_id"] == str(owner_id)
        assert created_events[0]["type"] == "FOLDER"

        # 2. move_node
        stream.seek(0)
        stream.truncate(0)
        mock_node = MagicMock(
            id=node_id,
            owner_id=owner_id,
            parent_id=parent_id,
            role=NodeRole.NORMAL,
            space=NodeSpace.PERSONAL,
            type=NodeType.FOLDER,
            updated_at=None,
        )
        new_parent_id = uuid4()

        def do_move(s, n, d, c):
            n.parent_id = new_parent_id
            return None

        with (
            patch("pycil.library.nodes.lock_owner", AsyncMock()),
            patch("pycil.library.nodes.owned", AsyncMock(return_value=mock_node)),
            patch("pycil.library.nodes.move_locked", AsyncMock(side_effect=do_move)),
            patch("pycil.library.nodes.row_data", lambda n: {"id": node_id}),
        ):
            await move_node(
                mock_session, owner_id, node_id, NodeMove(parent_id=new_parent_id), mock_config
            )

        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        moved_events = [entry for entry in lines if entry["event"] == "library_node_moved"]
        assert len(moved_events) == 1
        assert moved_events[0]["node_id"] == str(node_id)
        assert moved_events[0]["old_parent_id"] == str(parent_id)
        assert moved_events[0]["new_parent_id"] == str(new_parent_id)

        # 3. delete_node
        stream.seek(0)
        stream.truncate(0)
        with (
            patch("pycil.library.nodes.lock_owner", AsyncMock()),
            patch("pycil.library.nodes.owned", AsyncMock(return_value=mock_node)),
            patch("pycil.library.nodes.delete_subtree", AsyncMock()),
        ):
            await delete_node(mock_session, owner_id, node_id, mock_config)

        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        deleted_events = [entry for entry in lines if entry["event"] == "library_node_deleted"]
        assert len(deleted_events) == 1
        assert deleted_events[0]["node_id"] == str(node_id)
        assert deleted_events[0]["node_type"] == mock_node.type.value

        # 4. replace_membership
        stream.seek(0)
        stream.truncate(0)
        deck_node = MagicMock(id=node_id, owner_id=owner_id)
        with patch("pycil.library.nodes.select", MagicMock()):
            mock_session.scalars.side_effect = [
                MagicMock(all=MagicMock(return_value=[1, 2])),  # present
                MagicMock(all=MagicMock(return_value=[3])),  # existing additions
            ]
            final = await replace_membership(mock_session, deck_node, [2, 3], mock_config)
            assert final == [2, 3]

        lines = [json.loads(line) for line in stream.getvalue().strip().splitlines()]
        mod_events = [entry for entry in lines if entry["event"] == "library_deck_senses_modified"]
        assert len(mod_events) == 1
        assert mod_events[0]["deck_id"] == str(node_id)
        assert mod_events[0]["owner_id"] == str(owner_id)
        assert mod_events[0]["added_count"] == 1
        assert mod_events[0]["removed_count"] == 1
        assert mod_events[0]["total_count"] == 2
    finally:
        root_logger.handlers = original_handlers
        clear_contextvars()
