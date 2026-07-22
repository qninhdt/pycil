"""Embedded-Lexi API composition seam tests."""

from types import SimpleNamespace

from pycil.content import deps


async def test_embedded_reader_factory_and_lifecycle(monkeypatch):
    disposed = False
    lexicon = SimpleNamespace(_engine=None)

    class Engine:
        async def dispose(self):
            nonlocal disposed
            disposed = True

    lexicon._engine = Engine()

    reader = object()
    monkeypatch.setattr(
        deps,
        "create_embedded_lexicon_reader",
        lambda: (lexicon, reader),
    )

    constructed_lexicon, constructed_reader = deps.create_embedded_lexi_reader()

    assert constructed_lexicon is lexicon
    assert constructed_reader is reader
    await deps.close_embedded_lexicon(constructed_lexicon)
    assert disposed is True


async def test_active_content_dependency_uses_one_embedded_reader(monkeypatch):
    lexicon, reader = object(), object()
    monkeypatch.setattr(deps, "_lexicon", None)
    monkeypatch.setattr(deps, "_client", None)
    monkeypatch.setattr(deps, "create_embedded_lexi_reader", lambda: (lexicon, reader))

    assert deps.get_lexi_client() is reader
    assert deps.get_lexi_client() is reader
    await deps.close_lexi_client()
    assert deps._lexicon is None
    assert deps._client is None
