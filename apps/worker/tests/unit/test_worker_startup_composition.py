"""Worker startup composition: the embedded Lexi engine and the resource lifecycle.

The worker embeds Lexi's domain library rather than calling it over the network, so
startup must construct exactly one engine and hand the reader and worker-engine
capabilities to jobs separately. These check that composition and that shutdown
closes what startup opened.
"""

from unittest.mock import AsyncMock

from pycil_worker import main


async def test_startup_constructs_one_embedded_lexi_engine(monkeypatch):
    """One Lexicon per worker, with its reader and worker engine derived from it."""
    lexicon = object()
    reader = object()
    worker_engine = object()
    redis = AsyncMock()

    monkeypatch.setattr(main.Lexicon, "from_settings", classmethod(lambda cls: lexicon))
    monkeypatch.setattr(main, "create_lexicon_reader", lambda value: reader)
    monkeypatch.setattr(main, "create_lexicon_worker_engine", lambda value: worker_engine)
    fake_redis_cls = type("R", (), {"from_url": staticmethod(lambda *a, **k: redis)})
    monkeypatch.setattr(main, "Redis", fake_redis_cls)
    monkeypatch.setattr(main, "create_async_engine", lambda *a, **k: AsyncMock())
    monkeypatch.setattr(main, "async_sessionmaker", lambda *a, **k: object())

    resources = await main._build_resources()

    assert resources["lexicon"] is lexicon
    assert resources["lexi_reader"] is reader
    assert resources["lexi_engine"] is worker_engine
    redis.ping.assert_awaited_once()


async def test_shutdown_closes_every_resource_it_opened(monkeypatch):
    lexicon = AsyncMock()
    engine = AsyncMock()
    redis = AsyncMock()

    await main._close_resources({"lexicon": lexicon, "engine": engine, "redis": redis})

    lexicon.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    redis.aclose.assert_awaited_once()


async def test_shutdown_tolerates_resources_that_never_started():
    """A failure during startup must still be able to run the same cleanup."""
    await main._close_resources({})


def test_registration_covers_every_contract_kind():
    """A kind with no handler would leave a published job unhandled forever."""
    registered = set(main.broker.get_all_tasks())
    assert registered == {"generate_word_task", "prepare_questions_task"}


def test_a_registry_gap_is_refused(monkeypatch):
    """The worker must fail loudly rather than silently serve a subset."""
    monkeypatch.setattr(main, "_HANDLERS", {"word": main.generate_word})
    try:
        main._register_jobs()
    except RuntimeError as exc:
        assert "worker_handler_registry_mismatch" in str(exc)
    else:  # pragma: no cover - the assertion above is the point
        raise AssertionError("a missing handler registration must refuse to start")
