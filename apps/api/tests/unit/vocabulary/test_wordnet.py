import wn

from pycil.vocabulary.references.wordnet import lookup


async def test_missing_local_corpus_is_optional_and_never_downloads(monkeypatch):
    def missing(citation):
        raise LookupError("local corpus unavailable")

    monkeypatch.setattr(wn, "synsets", missing)
    assert await lookup("bank") == []
    assert await lookup("give {sb} a hand") == []


async def test_corpus_evidence_keeps_citation_identity_and_bounds_synsets(monkeypatch):
    requested = []

    class Synset:
        def __init__(self, number):
            self.number = number

        def name(self):
            return f"ice_cream.n.{self.number:02d}"

        def pos(self):
            return "n"

        def definition(self):
            return f"frozen dessert meaning {self.number}"

    def synsets(citation):
        requested.append(citation)
        return [Synset(number) for number in range(1, 23)]

    monkeypatch.setattr(wn, "synsets", synsets)
    evidence = await lookup("ice cream")
    assert requested == ["ice_cream"]
    assert len(evidence) == 20
    assert evidence[0] == {
        "key": "ice_cream.n.01",
        "pos": "n",
        "definition": "frozen dessert meaning 1",
    }
    assert evidence[-1]["key"] == "ice_cream.n.20"
