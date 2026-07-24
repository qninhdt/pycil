"""Embedded-Lexi API composition seam tests."""

from pycil.content import deps


class FakeLexicon:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


async def test_embedded_reader_factory_and_lifecycle(monkeypatch):
    lexicon = FakeLexicon()
    reader = object()
    monkeypatch.setattr(deps, "create_embedded_lexicon_reader", lambda: (lexicon, reader))

    constructed_lexicon, constructed_reader = deps.create_embedded_lexi_reader()

    assert constructed_lexicon is lexicon
    assert constructed_reader is reader
    await deps.close_embedded_lexicon(constructed_lexicon)
    assert lexicon.closed is True


async def test_active_content_dependency_uses_one_embedded_reader(monkeypatch):
    lexicon, reader = FakeLexicon(), object()
    monkeypatch.setattr(deps, "_lexicon", None)
    monkeypatch.setattr(deps, "_client", None)
    monkeypatch.setattr(deps, "create_embedded_lexi_reader", lambda: (lexicon, reader))

    assert deps.get_lexi_client() is reader
    assert deps.get_lexi_client() is reader
    await deps.close_lexi_client()
    assert lexicon.closed is True
    assert deps._lexicon is None
    assert deps._client is None
