import asyncio
import socket
from types import SimpleNamespace
from uuid import uuid7

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import event
from taskiq import TaskiqResult
from taskiq.depends.progress_tracker import TaskProgress, TaskState
from taskiq.receiver import Receiver

from pycil.account.auth import current_user_id
from pycil.app.broker import (
    CONSUMER_GROUP_NAME,
    TASK_RESULT_PREFIX,
    TASK_STREAM_KEY,
    RetryableJobError,
    create_broker,
)
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.app.settings import WorkerSettings
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.jobs.metadata import owner_key
from pycil.library.models import NodeRole
from pycil.study.schemas import Prepare
from pycil.study.tasks import request_preparation
from pycil.vocabulary.generation.tasks import word_generation_lock_key
from tests.support.account import account


@pytest.fixture
async def native_jobs(database, redis_store, redis_container):
    redis, namespace = redis_store
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0"
    config = load_config()
    deployment = WorkerSettings(
        db_url=SecretStr(database.url),
        redis_url=SecretStr(url),
        llm_api_key=SecretStr("test"),
        llm_base_url="https://provider.invalid/v1",
    )
    native = create_broker(config, deployment)
    native.queue_name = namespace + ":tasks"
    native.consumer_group_name = namespace + ":workers"
    native.result_backend.prefix_str = namespace + ":results"
    native.state.config = config
    native.state.resources = SimpleNamespace(redis=redis, sessions=database.sessions)
    try:
        await native.startup()
        yield native, redis, config
    finally:
        await native.shutdown()


async def execute_one(native):
    messages = native.listen()
    try:
        async with asyncio.timeout(5):
            message = await anext(messages)
            await Receiver(native, run_startup=False).callback(message)
    finally:
        await messages.aclose()


async def test_native_retry_is_selective_same_id_and_hides_intermediate_failure(native_jobs):
    native, redis, config = native_jobs
    attempts = []

    @native.task(task_name="test.safe_retry", retry_on_error=True, max_retries=2)
    async def retrying():
        attempts.append(1)
        if len(attempts) == 1:
            raise RetryableJobError("job_dependencies_unavailable") from None
        return {"word_id": 4}

    handle = await retrying.kiq()
    await execute_one(native)
    assert not await native.result_backend.is_result_ready(handle.task_id)
    await execute_one(native)
    assert (await handle.get_result()).return_value == {"word_id": 4}
    assert len(attempts) == 2

    @native.task(task_name="test.retry_exhausted", retry_on_error=True, max_retries=2)
    async def exhausted():
        attempts.append(1)
        raise RetryableJobError("job_dependencies_unavailable") from None

    handle = await exhausted.kiq()
    await execute_one(native)
    await execute_one(native)
    assert (await handle.get_result()).is_err and len(attempts) == 4

    @native.task(task_name="test.terminal", retry_on_error=True, max_retries=2)
    async def terminal():
        attempts.append(1)
        raise RuntimeError("provider_budget_exhausted") from None

    handle = await terminal.kiq()
    await execute_one(native)
    assert (await handle.get_result()).is_err and len(attempts) == 5


@pytest.mark.parametrize("kind", ["word", "preparation"])
async def test_database_connection_refusal_retries_before_domain_work(
    native_jobs, database, tmp_path, kind
):
    from pycil.vocabulary.generation.tasks import request_generation
    from pycil.vocabulary.references.importer import import_reference
    from pycil.vocabulary.references.reference import encode_reference_id
    from tests.support.inference import WordProvider
    from tests.support.reference import reference_file, reference_word

    native, redis, config = native_jobs
    user, roots = await account(database.sessions)
    provider = WordProvider()
    resources = native.state.resources
    resources.structured_llm = provider
    resources.word_store = InMemoryStore(max_entries=10, ttl=30)
    resources.artifact_store = resources.sense_store = None
    if kind == "word":
        await import_reference(
            database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
        )
        accepted = await request_generation(
            database.sessions, redis, native, config, user.id, encode_reference_id(1)
        )
    else:
        accepted = await request_preparation(
            database.sessions,
            redis,
            native,
            config,
            user.id,
            Prepare(node_id=roots[NodeRole.LIBRARY_ROOT].id),
        )
    await database.engine.dispose()
    failures = []
    # Reserve a non-listening port so the first checkout gets a real driver connection error.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))

        @event.listens_for(database.engine.sync_engine, "do_connect", once=True)
        def refuse_first_connection(dialect, connection_record, args, kwargs):
            try:
                return dialect.connect(
                    *args, **(kwargs | {"host": "127.0.0.1", "port": unavailable.getsockname()[1]})
                )
            except ConnectionRefusedError as error:
                failures.append(type(error))
                raise

        await execute_one(native)
    job_id = str(accepted.job_id)
    assert failures == [ConnectionRefusedError]
    assert provider.calls == 0
    assert not await native.result_backend.is_result_ready(job_id)
    assert await redis.xlen(native.queue_name) == 2
    await execute_one(native)
    result = await native.result_backend.get_result(job_id)
    assert not result.is_err
    if kind == "word":
        assert result.return_value["word_id"] > 0 and provider.calls == 2
    else:
        assert result.return_value["actual_question_count"] == 0 and provider.calls == 0
    assert await redis.xlen(native.queue_name) == 2


async def test_status_is_owner_only_result_wins_and_polling_does_not_extend_ttl(
    native_jobs,
    database,
):
    native, redis, config = native_jobs
    user, _ = await account(database.sessions)
    other, _ = await account(database.sessions)
    app = create_app()
    app.state.redis, app.state.broker = redis, native
    viewer = [user.id]
    app.dependency_overrides[current_user_id] = lambda: viewer[0]
    job_id = str(uuid7())
    await redis.set(owner_key(job_id), str(user.id), ex=60)
    await native.result_backend.set_progress(
        job_id, TaskProgress(state=TaskState.STARTED, meta=None)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as client:
        url = f"/v1/jobs/{job_id}"
        assert (await client.get(url)).json()["status"] == "running"
        await native.result_backend.set_result(
            job_id, TaskiqResult(is_err=False, return_value={"word_id": 7}, execution_time=0.1)
        )
        assert (await client.get(url)).json()["result"] == {"word_id": 7}
        assert await redis.ttl(owner_key(job_id)) <= 60
        viewer[0] = other.id
        denied = await client.get(url)
        unknown = await client.get(f"/v1/jobs/{uuid7()}")
        assert denied.status_code == unknown.status_code == 404
        assert denied.json()["code"] == unknown.json()["code"] == "job_not_found"
        viewer[0] = user.id
        await redis.delete(owner_key(job_id))
        assert (await client.get(url)).status_code == 404


async def test_preparation_request_coalesces_effective_options_and_native_result_roundtrips(
    native_jobs,
    database,
):
    native, redis, config = native_jobs
    user, roots = await account(database.sessions)
    data = Prepare(node_id=roots[NodeRole.LIBRARY_ROOT].id)
    first, same = await asyncio.gather(
        *(
            request_preparation(database.sessions, redis, native, config, user.id, data)
            for _ in range(2)
        )
    )
    assert first == same and await redis.xlen(native.queue_name) == 1
    # Native Context supplies live resources; preparation has no eligible senses/LLM calls.
    resources = native.state.resources
    resources.structured_llm = object()
    resources.artifact_store = resources.sense_store = None
    await execute_one(native)
    result = await native.result_backend.get_result(str(first.job_id))
    assert not result.is_err and result.return_value["actual_question_count"] == 0
    assert result.return_value["node_id"] == str(roots[NodeRole.LIBRARY_ROOT].id)
    changed = await request_preparation(
        database.sessions,
        redis,
        native,
        config,
        user.id,
        Prepare(node_id=roots[NodeRole.LIBRARY_ROOT].id, questions_per_sense=1, max_sense_count=1),
    )
    assert changed.job_id != first.job_id


@pytest.mark.skip(
    reason=(
        "User deferred idle crash recovery; taskiq-redis 1.2.4 needs fresh traffic. "
        "Revisit after worker implementation."
    )
)
async def test_idle_queue_recovers_pending_delivery_after_worker_crash(native_jobs):
    native, redis, config = native_jobs
    # shortcut: known upstream idle reclaim defect; enable after selecting a fixed release.
    native.idle_timeout = 10
    native.block = 50

    @native.task(task_name="test.crash_reclaim")
    async def probe():
        return "recovered"

    handle = await probe.kiq()
    first = native.listen()
    await anext(first)
    await first.aclose()  # Delivery was read but never acknowledged, as after a crash.
    await asyncio.sleep(0.05)
    await execute_one(native)  # No new messages are published to trigger reclaim.
    assert (await handle.get_result()).return_value == "recovered"


async def test_native_cli_worker_has_no_api_secrets_and_runs_four_jobs_before_draining(
    native_jobs,
    database,
    redis_container,
    tmp_path,
):
    import os
    import signal
    import subprocess
    import sys
    from pathlib import Path

    from pycil.vocabulary.references.importer import import_reference
    from tests.support.job_worker import probe
    from tests.support.reference import reference_file, reference_word

    native, redis, config = native_jobs
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    native.queue_name, native.consumer_group_name = TASK_STREAM_KEY, CONSUMER_GROUP_NAME
    native.result_backend.prefix_str = TASK_RESULT_PREFIX
    key = "test:cli-active:" + str(uuid7())
    handles = [await probe.kicker().with_broker(native).kiq(key, 1.0) for _ in range(4)]
    env = {
        "PATH": os.environ["PATH"],
        "DB_URL": database.url,
        "REDIS_URL": f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0",
        "LLM_API_KEY": "test-only",
        "LLM_BASE_URL": "https://provider.invalid/v1",
        "PYTHONPATH": str(Path(__file__).resolve().parents[3]),
    }
    log = tmp_path / "worker.log"
    process = None
    try:
        with log.open("w") as output:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "taskiq",
                    "worker",
                    "pycil.app.broker:worker_broker",
                    "pycil.vocabulary.generation.tasks",
                    "pycil.study.tasks",
                    "tests.support.job_worker",
                    "--workers",
                    "1",
                    "--max-async-tasks",
                    "4",
                    "--max-prefetch",
                    "0",
                    "--ack-type",
                    "when_saved",
                    "--wait-tasks-timeout",
                    "3",
                    "--shutdown-timeout",
                    "5",
                    "--no-configure-logging",
                ],
                env=env,
                cwd=Path(__file__).resolve().parents[3],
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            async with asyncio.timeout(15):
                while int(await redis.get(key) or 0) < 4:
                    assert process.poll() is None, log.read_text()
                    await asyncio.sleep(0.05)
            os.killpg(process.pid, signal.SIGTERM)
            results = await asyncio.gather(*(handle.wait_result(timeout=10) for handle in handles))
            assert all(result.return_value == "finished" for result in results)
            await asyncio.to_thread(process.wait, 12)
        assert process.returncode == 0, log.read_text()
        logs = log.read_text()
        assert "search_index_started" not in logs
        assert "resources_closed" in logs
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            await asyncio.to_thread(process.wait, 5)
        await redis.delete(key)


async def test_word_tasks_keep_owner_private_and_singleflight_cross_user_work(
    native_jobs,
    database,
    tmp_path,
):
    from pycil.vocabulary.generation.tasks import request_generation
    from pycil.vocabulary.references.importer import import_reference
    from pycil.vocabulary.references.reference import encode_reference_id
    from tests.support.inference import WordProvider
    from tests.support.reference import reference_file, reference_word

    native, redis, config = native_jobs
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    users = [(await account(database.sessions))[0] for _ in range(2)]
    reference = encode_reference_id(1)
    jobs = await asyncio.gather(
        *(
            request_generation(database.sessions, redis, native, config, user.id, reference)
            for user in users
        )
    )
    assert jobs[0].job_id != jobs[1].job_id
    provider = WordProvider()
    native.state.resources.structured_llm = provider
    native.state.resources.word_store = InMemoryStore(max_entries=10, ttl=30)
    native.state.resources.sense_store = None
    listener = native.listen()
    try:
        messages = [await anext(listener) for _ in range(2)]
        await asyncio.gather(
            *(Receiver(native, run_startup=False).callback(message) for message in messages)
        )
    finally:
        await listener.aclose()
    results = [await native.result_backend.get_result(str(job.job_id)) for job in jobs]
    assert not any(result.is_err for result in results)
    assert results[0].return_value == results[1].return_value
    assert provider.calls == 2  # One inventory and one enrichment, across both users.
    assert not await redis.exists(word_generation_lock_key(reference))


async def test_ambiguous_publish_keeps_owner_but_does_not_reuse_an_unconfirmed_pointer(
    native_jobs,
    database,
    monkeypatch,
):
    from pycil.app.http import Problem

    native, redis, config = native_jobs
    user, roots = await account(database.sessions)
    ids = []

    def identifier():
        value = str(uuid7())
        ids.append(value)
        return value

    async def lost_reply(message):
        raise TimeoutError("private-redis-connection")

    native.with_id_generator(identifier)
    with monkeypatch.context() as patch:
        patch.setattr(native, "kick", lost_reply)
        with pytest.raises(Problem, match="job_submission_unavailable"):
            await request_preparation(
                database.sessions,
                redis,
                native,
                config,
                user.id,
                Prepare(node_id=roots[NodeRole.LIBRARY_ROOT].id),
            )
    assert await redis.get(owner_key(ids[0])) == str(user.id).encode()
    accepted = await request_preparation(
        database.sessions,
        redis,
        native,
        config,
        user.id,
        Prepare(node_id=roots[NodeRole.LIBRARY_ROOT].id),
    )
    assert str(accepted.job_id) != ids[0]
    assert await redis.xlen(native.queue_name) == 1


async def test_native_result_store_failure_can_ack_without_a_result(native_jobs, monkeypatch):
    native, redis, config = native_jobs

    @native.task(task_name="test.result_write_failure")
    async def completed():
        return "completed"

    handle = await completed.kiq()

    async def failed_save(*args):
        raise RuntimeError("controlled_result_store_outage")

    with monkeypatch.context() as patch:
        patch.setattr(native.result_backend, "set_result", failed_save)
        await execute_one(native)
    assert not await native.result_backend.is_result_ready(handle.task_id)
    pending = await redis.xpending(native.queue_name, native.consumer_group_name)
    assert pending["pending"] == 0  # Explicit upstream limitation; when_saved is not atomic.


async def test_domain_errors_are_sanitized_before_native_result_and_expired_jobs_do_no_work(
    native_jobs,
    database,
):
    from pycil.study.tasks import prepare_task

    native, redis, config = native_jobs
    user, roots = await account(database.sessions)
    handle = (
        await prepare_task.kicker()
        .with_broker(native)
        .kiq(
            user_id=str(user.id),
            node_id=str(roots[NodeRole.LIBRARY_ROOT].id),
            selection="private-invalid-selection",
            preferences={"private": "payload"},
        )
    )
    await execute_one(native)
    result = await handle.get_result()
    assert result.is_err
    raw = await redis.get(native.result_backend._task_name(handle.task_id))
    assert b"private-invalid-selection" not in raw and b'"private"' not in raw
    assert b"study_preparation_failed" in raw


async def test_native_telemetry_propagates_http_context_and_closes_retry_spans(
    native_jobs,
    database,
    monkeypatch,
):
    from functools import partial

    from fastapi import APIRouter
    from opentelemetry import trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from sqlalchemy import text
    from taskiq.middlewares.opentelemetry_middleware import OpenTelemetryMiddleware

    from pycil.app import http
    from pycil.infrastructure import database as storage
    from pycil.infrastructure import observability

    native, redis, config = native_jobs
    spans = InMemorySpanExporter()
    tracer = TracerProvider(shutdown_on_exit=False)
    tracer.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    native.add_middlewares(OpenTelemetryMiddleware(tracer_provider=tracer, meter_provider=meter))
    monkeypatch.setattr(storage, "_query_tracer", tracer.get_tracer("pycil.database"))
    monkeypatch.setattr(observability, "_http_tracer", tracer.get_tracer("pycil.http.client"))
    monkeypatch.setattr(
        http,
        "OpenTelemetryMiddleware",
        partial(
            http.OpenTelemetryMiddleware,
            tracer_provider=tracer,
            meter_provider=meter,
        ),
    )
    attempts = []

    @native.task(task_name="test.traced_retry", retry_on_error=True, max_retries=2)
    async def probe():
        attempts.append(1)
        async with database.sessions() as session:
            assert await session.scalar(text("SELECT 1")) == 1
        from httpx import MockTransport, Response

        async with observability.ObservedAsyncClient(
            transport=MockTransport(lambda request: Response(200, json={"ok": True})),
        ) as client:
            assert (
                await client.get("https://private-provider.invalid/private-input")
            ).status_code == 200
        if len(attempts) == 1:
            raise RetryableJobError("job_dependencies_unavailable") from None
        return "done"

    app = create_app()
    app.state.config = config
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    router = APIRouter()

    @router.post("/controlled/publish")
    async def publish():
        handle = await probe.kiq()
        return {"task_id": handle.task_id}

    app.include_router(router)
    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://api.test") as client:
            response = await client.post("/controlled/publish")
        assert response.status_code == 200
        for _ in range(2):
            await execute_one(native)
            assert not trace.get_current_span().get_span_context().is_valid
        finished = spans.get_finished_spans()
        server = next(s for s in finished if s.kind == trace.SpanKind.SERVER)
        consumers = [s for s in finished if s.name == "execute/test.traced_retry"]
        sends = [s for s in finished if s.name == "send/test.traced_retry"]
        sql = [s for s in finished if s.name == "SELECT"]
        outbound = [s for s in finished if s.name == "GET" and s.kind == trace.SpanKind.CLIENT]
        assert len(consumers) == len(sends) == len(sql) == len(outbound) == 2
        assert all(s.context.trace_id == server.context.trace_id for s in finished)
        assert sends[0].parent.span_id == server.context.span_id
        assert consumers[0].parent.span_id == sends[0].context.span_id
        assert all(s.parent.span_id in {c.context.span_id for c in consumers} for s in sql)
        assert all(s.parent.span_id in {c.context.span_id for c in consumers} for s in outbound)
        assert "private-" not in str([span.to_json() for span in finished])
        measurements = {
            m.name: m
            for r in reader.get_metrics_data().resource_metrics
            for scope in r.scope_metrics
            for m in scope.metrics
        }
        assert sum(p.value for p in measurements["task_errors"].data.data_points) == 1
        assert sum(p.value for p in measurements["task_success"].data.data_points) == 1
        assert sum(p.value for p in measurements["worker_active_tasks"].data.data_points) == 0
        assert sum(p.count for p in measurements["task_execution_time"].data.data_points) == 2
        for metric in measurements.values():
            assert all("task_id" not in p.attributes for p in metric.data.data_points)
    finally:
        tracer.shutdown()
        meter.shutdown()


async def test_http_preparation_accepts_then_exposes_native_result_and_safe_store_failure(
    native_jobs,
    database,
    monkeypatch,
):
    from redis.exceptions import ConnectionError

    native, redis, config = native_jobs
    user, roots = await account(database.sessions)
    app = create_app()
    app.state.config = config
    app.state.redis, app.state.broker = redis, native
    app.state.sessions = database.sessions
    app.dependency_overrides[current_user_id] = lambda: user.id
    native.state.resources.structured_llm = object()
    native.state.resources.artifact_store = native.state.resources.sense_store = None
    async with AsyncClient(transport=ASGITransport(app), base_url="http://api.test") as client:
        accepted = await client.post(
            "/v1/study:prepare",
            json={"node_id": str(roots[NodeRole.LIBRARY_ROOT].id)},
        )
        assert accepted.status_code == 202
        assert accepted.headers["Location"] == accepted.json()["status_url"]
        assert accepted.headers["Retry-After"] == "2"
        url = accepted.json()["status_url"]
        assert (await client.get(url)).json()["status"] == "queued"
        await execute_one(native)
        response = await client.get(url)
        assert response.json()["status"] == "succeeded"
        assert response.json()["result"]["actual_question_count"] == 0

        async def unavailable(*args, **kwargs):
            raise ConnectionError("private-store-address")

        with monkeypatch.context() as patch:
            patch.setattr(redis, "get", unavailable)
            response = await client.get(url)
        assert response.status_code == 503
        assert response.json()["code"] == "job_status_unavailable"
        assert "private-store-address" not in response.text


async def test_provider_failure_is_private_and_does_not_retry_paid_work(
    native_jobs,
    database,
    tmp_path,
):
    from pycil.vocabulary.generation.tasks import request_generation
    from pycil.vocabulary.references.importer import import_reference
    from pycil.vocabulary.references.reference import encode_reference_id
    from tests.support.reference import reference_file, reference_word

    native, redis, config = native_jobs
    await import_reference(
        database.sessions,
        reference_file(tmp_path / "reference.jsonl", [reference_word()]),
    )
    user, _ = await account(database.sessions)

    class UnavailableProvider:
        calls = 0

        async def complete(self, *args):
            self.calls += 1
            raise RuntimeError("private-provider-output")

    provider = UnavailableProvider()
    native.state.resources.structured_llm = provider
    native.state.resources.word_store = InMemoryStore(max_entries=10, ttl=30)
    native.state.resources.sense_store = None
    accepted = await request_generation(
        database.sessions,
        redis,
        native,
        config,
        user.id,
        encode_reference_id(1),
    )
    await execute_one(native)
    result = await native.result_backend.get_result(str(accepted.job_id))
    assert result.is_err and provider.calls == 1
    raw = await redis.get(native.result_backend._task_name(str(accepted.job_id)))
    assert b"private-provider-output" not in raw
    assert b"word_generation_failed" in raw
    assert await redis.xlen(native.queue_name) == 1


async def test_native_timeout_ends_an_attempt_without_task_level_retry(native_jobs):
    native, redis, config = native_jobs

    @native.task(task_name="test.deadline", timeout=0.01, retry_on_error=True, max_retries=2)
    async def slow():
        await asyncio.sleep(1)

    handle = await slow.kiq()
    await execute_one(native)
    assert (await handle.get_result()).is_err
    assert await redis.xlen(native.queue_name) == 1


async def test_assistant_generation_waits_for_batch_and_returns_partial_results(
    native_jobs, database, tmp_path
):
    from pycil.assistant.tools import MUTATION_TOOLS, tools
    from pycil.vocabulary.references.importer import import_reference
    from pycil.vocabulary.search import SearchIndex
    from tests.support.inference import WordProvider
    from tests.support.reference import reference_file, reference_word

    native, redis, config = native_jobs
    await import_reference(
        database.sessions,
        reference_file(
            tmp_path / "reference.jsonl", [reference_word(1, 101), reference_word(2, 102)]
        ),
    )
    user, _ = await account(database.sessions)
    resources = native.state.resources
    resources.broker = native
    resources.structured_llm = WordProvider()
    resources.word_store = InMemoryStore(max_entries=10, ttl=30)
    resources.sense_store = InMemoryStore(max_entries=10, ttl=30)
    index = resources.search = SearchIndex(database.sessions)
    await index.start()
    invocation = None
    listener = native.listen()
    try:
        surface = {tool.name: tool for tool in tools(resources, user.id, config)}
        assert "generate_words" in MUTATION_TOOLS
        assert not {"get_generations", "prepare_study", "generate_word"} & surface.keys()
        hits = await surface["search_words"].ainvoke({"queries": ["bank"]})
        references = [item["reference_id"] for item in hits["items"]]
        assert len(references) == 2
        invocation = asyncio.create_task(
            surface["generate_words"].ainvoke(
                {"reference_ids": [*references, references[0], "invalid"]}
            )
        )
        # Both entries must be published before either result exists: waiting is concurrent.
        async with asyncio.timeout(5):
            messages = [await anext(listener) for _ in range(2)]
        assert not invocation.done() and database.engine.pool.checkedout() == 0
        receiver = Receiver(native, run_startup=False)
        await receiver.callback(messages[0])
        second = native.serializer.loadb(messages[1].data)
        await native.result_backend.set_result(
            second["task_id"],
            TaskiqResult(
                is_err=True,
                return_value=None,
                error=RuntimeError("private-provider-detail"),
                execution_time=0,
            ),
        )
        await messages[1].ack()
        async with asyncio.timeout(5):
            completed = await invocation
        assert [item["status"] for item in completed["items"]] == ["succeeded", "failed", "failed"]
        item = completed["items"][0]
        assert item["word_id"] > 0 and item["senses"][0]["definition"] == "a financial institution"
        assert completed["items"][1]["error"] == "job_failed"
        assert completed["items"][2]["error"] == "invalid_reference"
        assert "private-provider-detail" not in str(completed)
    finally:
        if invocation is not None:
            invocation.cancel()
            await asyncio.gather(invocation, return_exceptions=True)
        await listener.aclose()
        await index.close()


async def test_assistant_wait_timeout_keeps_job_running_without_resubmission(
    native_jobs, database, tmp_path
):
    from pycil.assistant.tools import tools
    from pycil.vocabulary.references.importer import import_reference
    from pycil.vocabulary.references.reference import encode_reference_id
    from tests.support.reference import reference_file, reference_word

    native, redis, config = native_jobs
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    user, _ = await account(database.sessions)
    resources = native.state.resources
    resources.broker = native
    config = config.model_copy(
        update={
            "runtime": config.runtime.model_copy(
                update={
                    "jobs": config.runtime.jobs.model_copy(update={"timeout_seconds": 0.05}),
                }
            )
        }
    )
    surface = {tool.name: tool for tool in tools(resources, user.id, config)}
    data = {"reference_ids": [encode_reference_id(1)]}
    first = (await surface["generate_words"].ainvoke(data))["items"][0]
    second = (await surface["generate_words"].ainvoke(data))["items"][0]
    assert first["status"] == "pending" and first["job_id"] == second["job_id"]
    assert await redis.xlen(native.queue_name) == 1
    assert await redis.get(owner_key(first["job_id"])) == str(user.id).encode()
    assert not await native.result_backend.is_result_ready(first["job_id"])
