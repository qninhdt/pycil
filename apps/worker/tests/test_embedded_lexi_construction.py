"""Embedded-Lexi worker composition seam tests."""

from pycil_worker import main


async def test_embedded_worker_engine_factory_and_lifecycle(monkeypatch):
    class Lexicon:
        closed = False

        @classmethod
        def from_settings(cls):
            return cls()

        async def close(self):
            self.closed = True

    reader = object()
    worker_engine = object()
    monkeypatch.setattr(main, "Lexicon", Lexicon)
    monkeypatch.setattr(main, "create_lexicon_reader", lambda _value: reader)
    monkeypatch.setattr(main, "create_lexicon_worker_engine", lambda _value: worker_engine)

    lexicon, constructed_reader, constructed_engine = main.create_embedded_lexi_worker_engine()

    assert constructed_reader is reader
    assert constructed_engine is worker_engine
    await main.close_embedded_lexicon(lexicon)
    assert lexicon.closed is True


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
