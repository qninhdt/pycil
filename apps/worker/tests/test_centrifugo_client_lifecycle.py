"""The worker's broker client is one process-wide, lifecycle-managed resource."""

from pycil_worker import main


async def test_startup_injects_one_broker_client_and_shutdown_releases_it(monkeypatch):
    """on_startup builds a single adapter; on_shutdown closes that same instance.

    The relay runs on every pg notification and every cron sweep, so a client
    built per invocation would open and abandon a connection pool each time. The
    client must therefore live in ctx like the engine and the lexicon, and its
    close must be wired into shutdown next to them.
    """

    class FakeControl:
        closed = False

        async def close(self) -> None:
            self.closed = True

    control = FakeControl()

    async def no_op(_ctx):
        return None

    class FakeLexicon:
        async def close(self) -> None:
            return None

    class FakeEngine:
        async def dispose(self) -> None:
            return None

    monkeypatch.setattr(main, "CentrifugoControl", lambda: control)
    monkeypatch.setattr(main, "create_async_engine", lambda *_args, **_kwargs: FakeEngine())
    monkeypatch.setattr(main, "async_sessionmaker", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        main,
        "create_embedded_lexi_worker_engine",
        lambda: (FakeLexicon(), object(), object()),
    )
    monkeypatch.setattr(main, "heartbeat", no_op)
    monkeypatch.setattr(main, "_start_task_outbox_listener", no_op)
    monkeypatch.setattr(main, "_drain_task_outbox", no_op)
    monkeypatch.setattr(main, "reconcile_async_tasks", no_op)

    context = {}
    await main.on_startup(context)
    assert context["centrifugo"] is control

    await main.on_shutdown(context)
    assert control.closed is True


async def test_shutdown_tolerates_a_missing_broker_client():
    """Startup is incremental and shutdown must tolerate partial initialization."""

    class FakeControl:
        closed = False

        async def close(self) -> None:
            self.closed = True

    control = FakeControl()
    await main.on_shutdown({"centrifugo": control})
    assert control.closed is True
    # And absence — e.g. a crash before injection — must not raise either.
    await main.on_shutdown({})
