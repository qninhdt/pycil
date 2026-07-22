"""Inactive embedded-Lexi worker composition seam tests."""

import sys
from types import SimpleNamespace

from pycil_worker import main


async def test_embedded_worker_engine_factory_and_lifecycle(monkeypatch):
    disposed = False
    lexicon = SimpleNamespace(_engine=None)

    class Engine:
        async def dispose(self):
            nonlocal disposed
            disposed = True

    lexicon._engine = Engine()

    class Lexicon:
        @classmethod
        def from_settings(cls):
            return lexicon

    reader = object()
    worker_engine = object()
    monkeypatch.setitem(sys.modules, "lexi_ai", SimpleNamespace(Lexicon=Lexicon))
    monkeypatch.setattr(
        main,
        "create_lexicon_reader",
        lambda value: reader if value is lexicon else None,
    )
    monkeypatch.setattr(
        main,
        "create_lexicon_worker_engine",
        lambda value: worker_engine if value is lexicon else None,
    )

    constructed_lexicon, constructed_reader, constructed_engine = (
        main.create_embedded_lexi_worker_engine()
    )

    assert constructed_lexicon is lexicon
    assert constructed_reader is reader
    assert constructed_engine is worker_engine
    await main.close_embedded_lexicon(constructed_lexicon)
    assert disposed is True


async def test_startup_constructs_embedded_reader_and_engine(monkeypatch):
    async def no_op(_ctx):
        return None

    monkeypatch.setattr(main, "create_async_engine", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(main, "async_sessionmaker", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(main, "heartbeat", no_op)
    monkeypatch.setattr(main, "_start_task_outbox_listener", no_op)
    monkeypatch.setattr(main, "_drain_task_outbox", no_op)
    monkeypatch.setattr(main, "reconcile_async_tasks", no_op)
    lexicon, reader, worker_engine = object(), object(), object()
    monkeypatch.setattr(
        main,
        "create_embedded_lexi_worker_engine",
        lambda: (lexicon, reader, worker_engine),
    )

    context = {}
    await main.on_startup(context)

    assert context["lexicon"] is lexicon
    assert context["lexi_reader"] is reader
    assert context["lexi_engine"] is worker_engine
