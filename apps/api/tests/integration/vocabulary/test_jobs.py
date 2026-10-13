import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid7

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from structlog import get_logger

from pycil.account.auth import actor
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.app.http import Problem
from pycil.infrastructure.cache import RedisCache
from pycil.vocabulary.enums import GenerationStage, JobState
from pycil.vocabulary.generation import jobs


@pytest.fixture
def manager(redis_store):
    redis, namespace = redis_store

    def create():
        config = SimpleNamespace(
            generation=SimpleNamespace(timeout_seconds=10, examples_per_sense=1)
        )
        return jobs.Generations(None, None, None, None, config, store=RedisCache(redis, namespace))

    return create


async def test_normalized_singleflight_and_ready_status_follow_completed_publication(
    monkeypatch, manager
):
    started, finish = asyncio.Event(), asyncio.Event()
    calls = 0

    async def pipeline(*args, **options):
        nonlocal calls
        calls += 1
        started.set()
        await finish.wait()
        return SimpleNamespace(id=7, senses=[SimpleNamespace(id=8)])

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    try:
        first = await generations.submit("bank")
        await started.wait()
        second = await generations.submit(" BANK ")
        assert first["task_id"] == second["task_id"]
        assert (await generations.status(first["task_id"]))["status"] is JobState.RUNNING
        finish.set()
        await generations.wait([first["task_id"]])
        result = await generations.status(first["task_id"])
        assert calls == 1
        assert result["word_id"] == 7
        assert result["status"] is JobState.SUCCEEDED
        assert result["stage"] is GenerationStage.READY
    finally:
        await generations.close()


async def test_configured_deadline_cancels_and_joins_pipeline_before_failure(monkeypatch, manager):
    cleaned = asyncio.Event()

    async def pipeline(*args, **options):
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    generations.config.generation.timeout_seconds = 0.01
    try:
        submitted = await generations.submit("bank")
        async with asyncio.timeout(1):
            await cleaned.wait()
            await asyncio.gather(*(task for _, task in generations.flights.values()))
        result = await generations.status(submitted["task_id"])
        assert result["status"] is JobState.FAILED
        assert result["error"] == "generation_timeout" and result["word_id"] is None
        assert not generations.flights
    finally:
        await generations.close()


async def test_reference_identity_singleflight_does_not_merge_distinct_selections(
    monkeypatch, manager
):
    finish = asyncio.Event()

    async def reference(*args):
        return SimpleNamespace(id=args[-1])

    async def pipeline(*args, **options):
        await finish.wait()
        return SimpleNamespace(id=options["reference_id"], senses=[SimpleNamespace(id=8)])

    monkeypatch.setattr(jobs, "fetch_reference", reference)
    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    try:
        first = await generations.submit("bank", reference_id=11)
        same = await generations.submit(" BANK ", reference_id=11)
        other = await generations.submit("bank", reference_id=12)
        assert first["task_id"] == same["task_id"] != other["task_id"]
        finish.set()
        await generations.wait([first["task_id"], other["task_id"]])
        assert (await generations.status(first["task_id"]))["word_id"] == 11
        assert (await generations.status(other["task_id"]))["word_id"] == 12
    finally:
        await generations.close()


async def test_shutdown_cancels_and_joins_owned_work_before_returning(monkeypatch, manager):
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def pipeline(*args, **options):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    submitted = await generations.submit("bank")
    await started.wait()
    await generations.close()
    assert cleaned.is_set()
    assert not generations.flights
    result = await manager().status(submitted["task_id"])
    assert result["status"] is JobState.FAILED
    assert result["error"] == "generation_interrupted"
    with pytest.raises(Problem) as failure:
        await generations.submit("bank")
    assert failure.value.status == 503


@pytest.mark.parametrize("target", ["", "bad\u200bword", "{unknown}"])
async def test_invalid_generation_selection_creates_no_job(target, manager, redis_store):
    generations = manager()
    try:
        with pytest.raises(Problem) as error:
            await generations.submit(target)
        assert error.value.code == "invalid_generation_selection"
        assert not generations.flights
        redis, namespace = redis_store
        assert not [key async for key in redis.scan_iter(match=namespace + "*")]
    finally:
        await generations.close()


async def test_polling_another_instance_reads_running_and_completed_status(
    monkeypatch, manager, redis_store, redis_container
):
    finish = asyncio.Event()

    async def reference(*args):
        return SimpleNamespace()

    async def pipeline(*args, **options):
        await finish.wait()
        return SimpleNamespace(id=7, senses=[SimpleNamespace(id=8)])

    monkeypatch.setattr(jobs, "fetch_reference", reference)
    monkeypatch.setattr(jobs, "generate_word", pipeline)
    owner, observer = manager(), manager()
    remote = Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        socket_timeout=1,
        socket_connect_timeout=1,
    )
    observer.store = RedisCache(remote, redis_store[1])
    apps = [create_app(), create_app()]
    for app, generations in zip(apps, (owner, observer), strict=True):
        app.state.product = load_config()
        app.state.generations = generations
        app.dependency_overrides[actor] = lambda: None
    try:
        async with (
            AsyncClient(transport=ASGITransport(app=apps[0]), base_url="http://api.test") as submit,
            AsyncClient(transport=ASGITransport(app=apps[1]), base_url="http://api.test") as poll,
        ):
            response = await submit.post(
                "/v1/words:generate", json={"reference_id": "selected-reference", "target": "bank"}
            )
            assert response.status_code == 202
            accepted = response.json()
            assert not observer.flights
            running = await poll.get(accepted["status_url"])
            assert running.status_code == 200 and running.json() == accepted
            assert accepted["status"] == "running" and accepted["word_id"] is None
            finish.set()
            await owner.wait([UUID(accepted["task_id"])])
            await owner.close()
            completed = await poll.get(accepted["status_url"])
            assert completed.status_code == 200
            assert completed.json() == accepted | {
                "status": "succeeded",
                "stage": "ready",
                "word_id": 7,
            }
            missing = await poll.get(f"/v1/word-tasks/{uuid7()}")
            assert missing.status_code == 404
            assert missing.json() == {"error": "generation_not_found"}
    finally:
        await owner.close()
        await observer.close()
        await remote.aclose()


async def test_concurrent_submissions_still_share_one_local_flight(monkeypatch, manager):
    finish = asyncio.Event()
    calls = 0

    async def pipeline(*args, **options):
        nonlocal calls
        calls += 1
        await finish.wait()
        return SimpleNamespace(id=7, senses=[SimpleNamespace(id=8)])

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    try:
        results = await asyncio.gather(
            *(generations.submit(target) for target in ["bank", " BANK "] * 10)
        )
        identifiers = {result["task_id"] for result in results}
        assert len(identifiers) == 1 and calls == 1
        finish.set()
        await generations.wait(identifiers)
    finally:
        await generations.close()


async def test_shutdown_before_job_starts_publishes_interrupted_status(monkeypatch, manager):
    async def pipeline(*args, **options):
        pytest.fail("cancelled job must not start")

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    submitted = await generations.submit("bank")
    await generations.close()
    result = await manager().status(submitted["task_id"])
    assert result["status"] is JobState.FAILED
    assert result["error"] == "generation_interrupted"


async def test_shutdown_joins_final_status_publication(monkeypatch, manager, redis_store):
    publishing, finish = asyncio.Event(), asyncio.Event()
    redis, _namespace = redis_store
    native_set = redis.set
    writes = 0

    async def delayed_set(*args, **options):
        nonlocal writes
        writes += 1
        if writes == 2:
            publishing.set()
            await finish.wait()
        return await native_set(*args, **options)

    async def pipeline(*args, **options):
        return SimpleNamespace(id=7, senses=[SimpleNamespace(id=8)])

    monkeypatch.setattr(redis, "set", delayed_set)
    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    closing = None
    try:
        async with asyncio.timeout(2):
            submitted = await generations.submit("bank")
            await publishing.wait()
            closing = asyncio.create_task(generations.close())
            await asyncio.sleep(0)
            finish.set()
            await closing
            assert (await manager().status(submitted["task_id"]))["status"] is JobState.SUCCEEDED
    finally:
        finish.set()
        await generations.close()
        if closing is not None:
            await asyncio.gather(closing, return_exceptions=True)


async def test_status_ttl_expiry_missing_and_corrupt_values(manager, redis_store):
    generations = manager()
    redis, namespace = redis_store
    identifier = uuid7()
    with pytest.raises(Problem) as missing:
        await generations.status(identifier)
    assert missing.value.status == 404 and missing.value.code == "generation_not_found"
    result = dict(
        task_id=identifier,
        status=JobState.SUCCEEDED,
        word_id=7,
        stage=GenerationStage.READY,
        error=None,
        status_url=f"/v1/word-tasks/{identifier}",
    )
    key = f"{namespace}:word-tasks:{identifier}"
    await generations._save_status(result)
    assert 0 < await redis.ttl(key) <= 24 * 60 * 60
    await redis.pexpire(key, 1)
    await asyncio.sleep(0.02)
    with pytest.raises(Problem) as expired:
        await generations.status(identifier)
    assert expired.value.status == 404
    await redis.set(key, b"invalid JSON", ex=60)
    with pytest.raises(Problem) as corrupt:
        await generations.status(identifier)
    assert corrupt.value.status == 503 and corrupt.value.code == "generation_unavailable"


@pytest.mark.parametrize("phase", ["acceptance", "completion"])
async def test_redis_failure_does_not_start_untracked_work_or_hide_publication_failure(
    phase, monkeypatch, manager, redis_store, redis_container
):
    finish = asyncio.Event()
    calls = 0

    async def pipeline(*args, **options):
        nonlocal calls
        calls += 1
        await finish.wait()
        return SimpleNamespace(id=7, senses=[SimpleNamespace(id=8)])

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    rejected = Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        username=redis_store[1],
        password="private-test-credential",
        socket_timeout=1,
        socket_connect_timeout=1,
    )
    try:
        if phase == "completion":
            submitted = await generations.submit("bank")
        generations.store = RedisCache(rejected, redis_store[1])
        from structlog.testing import capture_logs

        with capture_logs() as logs:
            # A cached production logger retains its processors across prior tests.
            monkeypatch.setattr(jobs, "logger", get_logger("pycil.vocabulary.generation.jobs"))
            if phase == "acceptance":
                with pytest.raises(Problem) as failed:
                    await generations.submit("bank")
                assert failed.value.status == 503
                assert not generations.flights and calls == 0
            else:
                finish.set()
                await generations.wait([submitted["task_id"]])
                assert not generations.flights and calls == 1
                # A failed final write cannot claim success; the initial status remains.
                assert (await manager().status(submitted["task_id"]))["status"] is JobState.RUNNING
            with pytest.raises(Problem) as unavailable:
                await generations.status(uuid7())
            assert unavailable.value.status == 503
        assert {record["event"] for record in logs} >= {
            "word_generation_status_write_failed",
            "word_generation_status_read_failed",
        }
        assert "private-test-credential" not in str(logs)
    finally:
        await generations.close()
        await rejected.aclose()


@pytest.mark.parametrize(
    "failure, expected",
    [
        ("timeout", "generation_timeout"),
        ("provider", "generation_failed"),
        ("empty", "generation_failed"),
    ],
)
async def test_failed_generation_never_reports_ready_and_can_be_retried(
    monkeypatch, failure, expected, manager
):
    async def pipeline(*args, **options):
        if failure == "timeout":
            raise TimeoutError()
        if failure == "provider":
            raise RuntimeError("private provider detail")
        return SimpleNamespace(id=7, senses=[])

    monkeypatch.setattr(jobs, "generate_word", pipeline)
    generations = manager()
    try:
        first = await generations.submit("bank")
        await generations.wait([first["task_id"]])
        result = await generations.status(first["task_id"])
        assert result["status"] is JobState.FAILED
        assert result["stage"] is GenerationStage.WORD
        assert result["error"] == expected and result["word_id"] is None
        retry = await generations.submit("bank")
        assert retry["task_id"] != first["task_id"]
        await generations.wait([retry["task_id"]])
    finally:
        await generations.close()
