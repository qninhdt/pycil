"""Native lexical fixtures shared by integration tests and browser setup."""

import asyncio

import pytest
from lexi_ai import Lexicon, QuestionType
from lexi_ai.references.cambridge import encode_reference_id
from sqlalchemy import select, text

from pycil.vocabulary.generation import Generations
from tests.support.inference import LocalCompletion


async def fill(database, dictionary, config):
    lexicon, _ = dictionary
    manager = lexicon.test_generations
    manager.config = config
    results = await asyncio.gather(
        *(manager.submit("bank", reference_id=encode_reference_id(1)) for _ in range(3))
    )
    assert len({r["task_id"] for r in results}) == 1
    await asyncio.gather(*(task for _, task in list(manager.flights.values())))
    async with lexicon.db.read() as connection:
        from lexi_ai.schema import Sense

        ids = (await connection.scalars(select(Sense.id))).all()
    await lexicon.retrieve_question_artifacts(
        [(sid, kind, 1) for sid in ids for kind in QuestionType],
        generate=True,
        generation_batch_size=8,
    )
    return results[0]["task_id"]


@pytest.fixture
async def dictionary(database, reference, senses, config):
    engine, _, url = database
    import sqlite3

    with sqlite3.connect(reference) as connection:
        connection.execute("INSERT INTO words VALUES(1,'bank','bank','word','done')")
        connection.execute(
            "INSERT INTO entries(id,word_id,pos,definition,examples,entry_order) "
            "VALUES(1,1,'noun','financial institution','[]',1)"
        )
        connection.execute(
            "INSERT INTO senses(id,entry_id,definition,sense_order) "
            "VALUES(1,1,'financial institution',1)"
        )
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO lexi.word_references(word_id,source_id) VALUES(1,1)")
        )
        for table in ("words", "senses"):
            await connection.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('lexi.{table}','id'), "
                    f"(SELECT max(id) FROM lexi.{table}))"
                )
            )
    llm = LocalCompletion()
    value = Lexicon(db_url=url, db_schema="lexi", llm=llm)
    try:
        await value.import_reference(reference)
        await value.start()
        value.test_generations = Generations(value, config)
        yield value, llm
    finally:
        await value.test_generations.close()
        await value.close()
