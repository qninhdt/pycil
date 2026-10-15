import gzip

import pytest
from sqlalchemy import func, select

from pycil.vocabulary.references.importer import import_reference
from pycil.vocabulary.references.models import ReferenceSense, ReferenceWord
from tests.support.reference import reference_file, reference_word


async def test_import_retains_identity_and_identical_reimport(database, tmp_path):
    path = reference_file(tmp_path / "reference.jsonl", [reference_word()])
    first = await import_reference(database.sessions, path)
    assert await import_reference(database.sessions, path) == first
    assert first["words"] == first["senses"] == 1
    async with database.sessions() as session:
        word = await session.get(ReferenceWord, 1)
        sense = await session.get(ReferenceSense, 101)
        assert word.alternatives == [["banking", "variant"]]
        assert word.inflections == ["banks"]
        assert sense.word_id == word.id
        assert sense.definition == "a financial institution"
        assert sense.ipa_uk == "bæŋk"


async def test_conflict_rolls_back_new_rows(database, tmp_path):
    path = reference_file(tmp_path / "reference.jsonl", [reference_word()])
    await import_reference(database.sessions, path)
    reference_file(path, [reference_word(2, 102), reference_word(definition="changed identity")])
    with pytest.raises(ValueError, match="conflicts"):
        await import_reference(database.sessions, path)
    async with database.sessions() as session:
        assert await session.get(ReferenceWord, 2) is None
        assert (await session.get(ReferenceSense, 101)).definition == "a financial institution"


@pytest.mark.parametrize("failure", ["duplicate", "malformed"])
async def test_late_failure_rolls_back_flushed_batches(database, tmp_path, failure):
    records = [reference_word(i, 1000 + i) for i in range(1, 502)]
    path = reference_file(tmp_path / "reference.jsonl", records)
    with path.open("a") as stream:
        stream.write(
            '{"id":1}\n' if failure == "malformed" else path.read_text().splitlines()[0] + "\n"
        )
    with pytest.raises(ValueError):
        await import_reference(database.sessions, path)
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ReferenceWord)) == 0
        assert await session.scalar(select(func.count()).select_from(ReferenceSense)) == 0


async def test_reused_sense_identity_across_words_rolls_back_entire_import(database, tmp_path):
    path = reference_file(
        tmp_path / "reference.jsonl", [reference_word(1, 101), reference_word(2, 101)]
    )
    with pytest.raises(ValueError):
        await import_reference(database.sessions, path)
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ReferenceWord)) == 0
        assert await session.scalar(select(func.count()).select_from(ReferenceSense)) == 0


async def test_empty_reference_artifact_is_rejected(database, tmp_path):
    path = reference_file(tmp_path / "reference.jsonl", [])
    with pytest.raises(ValueError):
        await import_reference(database.sessions, path)


async def test_import_gzip_compressed_artifact(database, tmp_path):
    raw_path = reference_file(tmp_path / "reference.jsonl", [reference_word()])
    gz_path = tmp_path / "reference.jsonl.gz"
    with raw_path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
        dst.write(src.read())
    first = await import_reference(database.sessions, gz_path)
    assert first["words"] == first["senses"] == 1
    assert await import_reference(database.sessions, gz_path) == first
    async with database.sessions() as session:
        word = await session.get(ReferenceWord, 1)
        sense = await session.get(ReferenceSense, 101)
        assert word is not None and sense is not None
        assert word.lemma == "bank"
