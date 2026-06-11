"""Worker entrypoint coverage — import safety, WorkerSettings wiring, heartbeat.

The arq container boots via `arq worker.main.WorkerSettings`; an import error or
a malformed settings class crashes the worker on startup. The admin health
endpoint reports worker liveness from the heartbeat key written here, so the
heartbeat write is load-bearing for ops visibility.
"""
from __future__ import annotations

import pytest


def test_worker_settings_registers_all_jobs() -> None:
    from worker.main import WorkerSettings
    from worker.jobs.generate_term import generate_term
    from worker.jobs.generate_question import generate_question
    from worker.jobs.grade_answer import grade_answer
    from worker.jobs.prewarm_questions import prewarm_questions
    from worker.jobs.translate_definition import translate_definition
    from worker.jobs.tts_render import tts_render

    registered = set(WorkerSettings.functions)
    for fn in (
        generate_term,
        generate_question,
        grade_answer,
        prewarm_questions,
        translate_definition,
        tts_render,
    ):
        assert fn in registered, f"{fn.__name__} not registered on WorkerSettings"


def test_worker_settings_tunables() -> None:
    from worker.main import WorkerSettings

    assert WorkerSettings.max_tries == 2
    assert WorkerSettings.job_timeout == 90
    assert WorkerSettings.keep_result == 300
    # One cron job (the heartbeat) wired with run-at-startup.
    assert len(WorkerSettings.cron_jobs) == 1


def test_redis_settings_parses_dsn(monkeypatch) -> None:
    from worker.config import get_settings
    from worker.main import _redis_settings

    # Pin REDIS_URL explicitly so the test is deterministic regardless of the
    # ambient env (CI sets a real REDIS_URL that would otherwise win over the
    # conftest placeholder via pydantic-settings).
    monkeypatch.setenv("REDIS_URL", "redis://cache-host:6390/3")
    get_settings.cache_clear()
    try:
        settings = _redis_settings()
        assert settings.host == "cache-host"
        assert settings.port == 6390
        assert settings.database == 3
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_heartbeat_writes_key_with_ttl(arq_ctx) -> None:
    from worker.main import heartbeat, WORKER_HEARTBEAT_KEY, _HEARTBEAT_TTL_SECONDS

    await heartbeat(arq_ctx)

    redis = arq_ctx["redis"]
    value = await redis.get(WORKER_HEARTBEAT_KEY)
    assert value is not None
    # Stored as epoch-seconds string.
    assert float(value) > 0
    ttl = await redis.ttl(WORKER_HEARTBEAT_KEY)
    assert 0 < ttl <= _HEARTBEAT_TTL_SECONDS


def test_main_prints_arq_hint(capsys) -> None:
    from worker.main import main

    main()
    out = capsys.readouterr().out
    assert "arq" in out
