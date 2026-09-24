"""Embedded-Lexi API composition seam tests.

Patches `create_embedded_lexicon_reader` — the adapter this module calls — rather
than a forwarder in front of it. Two such forwarders used to exist in
`lexi_provider` only to be substituted from this file, which meant these tests
exercised a construction path production did not take.
"""

from pycil.ports import lexi_provider as deps


class FakeLexicon:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


async def test_the_reader_is_built_once_and_closed_on_shutdown(monkeypatch):
    """One Lexicon per process, and shutdown releases it.

    The caching matters beyond tidiness: `Lexicon.from_settings()` opens its own
    resources, so constructing per request would leak one set per call.
    """
    lexicon, reader = FakeLexicon(), object()
    builds = 0

    def build():
        nonlocal builds
        builds += 1
        return lexicon, reader

    monkeypatch.setattr(deps, "_lexicon", None)
    monkeypatch.setattr(deps, "_client", None)
    monkeypatch.setattr(deps, "create_embedded_lexicon_reader", build)

    assert deps.get_lexi_client() is reader
    assert deps.get_lexi_client() is reader
    assert builds == 1, "the reader must be constructed once per process, not per call"

    await deps.close_lexi_client()

    assert lexicon.closed is True
    assert deps._lexicon is None
    assert deps._client is None


async def test_closing_a_process_that_never_built_a_reader_is_safe(monkeypatch):
    """Shutdown runs even on a process that never served a request."""
    monkeypatch.setattr(deps, "_lexicon", None)
    monkeypatch.setattr(deps, "_client", None)

    await deps.close_lexi_client()
    await deps.close_lexi_client()

    assert deps._lexicon is None
    assert deps._client is None


async def test_a_closed_process_rebuilds_rather_than_serving_a_dead_reader(monkeypatch):
    """After close, the next caller gets a live reader, not the closed one."""
    first, second = FakeLexicon(), FakeLexicon()
    built = [(first, object()), (second, object())]

    monkeypatch.setattr(deps, "_lexicon", None)
    monkeypatch.setattr(deps, "_client", None)
    monkeypatch.setattr(deps, "create_embedded_lexicon_reader", lambda: built.pop(0))

    initial = deps.get_lexi_client()
    await deps.close_lexi_client()
    rebuilt = deps.get_lexi_client()

    assert first.closed is True
    assert rebuilt is not initial
    assert second.closed is False
