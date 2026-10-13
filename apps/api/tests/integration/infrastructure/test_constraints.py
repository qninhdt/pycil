import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from pycil.vocabulary.enums import ReferenceSource
from pycil.vocabulary.models import SenseReference
from pycil.vocabulary.references.importer import import_reference
from tests.support.reference import reference_file, reference_word
from tests.support.vocabulary import neutral_word


@pytest.mark.parametrize("citation", ["101", "0", "00101", "999999", "not-an-id"])
async def test_reference_citation_requires_existing_canonical_source_identity(
    database, tmp_path, citation
):
    await import_reference(
        database.sessions, reference_file(tmp_path / "reference.jsonl", [reference_word()])
    )
    _, sense_id = await neutral_word(database.sessions)

    async def insert():
        async with database.sessions() as session, session.begin():
            session.add(
                SenseReference(
                    sense_id=sense_id, source=ReferenceSource.REFERENCE, source_ref=citation
                )
            )

    if citation == "101":
        await insert()
    else:
        with pytest.raises(IntegrityError):
            await insert()
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(SenseReference)) == (
            1 if citation == "101" else 0
        )
