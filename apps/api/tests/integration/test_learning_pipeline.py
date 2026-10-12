import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from lexi_ai import Lexicon, QuestionArtifactType, QuestionType
from lexi_ai.references.cambridge import encode_reference_id
from sqlalchemy import select, text

from pycil.account.auth import actor, optional_actor
from pycil.account.models import User
from pycil.account.plans import Plan
from pycil.http import Problem
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from pycil.main import create_app
from pycil.study.models import UserSense
from pycil.study.preparation import prepare
from pycil.study.reviews import review
from pycil.study.schemas import ReviewBatch
from pycil.vocabulary.api import GenerationRequest
from pycil.vocabulary.generation import Generations


class LocalCompletion:
    """Deterministic inference boundary; native generation and storage remain real."""

    def __init__(self):
        self.calls = 0

    async def complete(self, instruction, data, schema):
        self.calls += 1
        c = json.loads(data.removeprefix("<artifact_context>").removesuffix("</artifact_context>"))
        word, definition = c["word"], c["definition"]
        model = schema.model_fields["artifacts"].annotation.__args__[0].__name__
        output = []
        for i in range(c.get("batch_size", 1)):
            wrong = [f"other{self.calls}_{i}_{j}" for j in range(c["distractor_count"])]
            if model == "WordDefinitionArtifact":
                payload = dict(
                    corrects=[
                        f"Paraphrase {self.calls}_{j}: {definition}"
                        for j in range(c["correct_count"])
                    ],
                    distractors=[dict(word=w, definition=f"another meaning {w}") for w in wrong],
                )
            elif model == "UsageArtifact":
                payload = dict(
                    corrects=[
                        f"The [{word}] is useful here ({self.calls}_{j})."
                        for j in range(c["correct_count"])
                    ],
                    distractors=[f"The [{word}] grows {w}." for w in wrong],
                )
            elif model == "ContextToWordArtifact":
                payload = dict(
                    context=f"Customer {self.calls}-{i} needed somewhere to deposit savings.",
                    distractors=wrong,
                )
            elif model == "ContextWordMeaningArtifact":
                payload = dict(
                    context=f"They visited the _ ({self.calls}-{i}).",
                    correct=dict(expression=word, meaning=definition),
                    distractors=[dict(expression=w, meaning=f"meaning of {w}") for w in wrong],
                )
            elif model == "DialogueArtifact":
                payload = dict(
                    conversation=[
                        {"Alex": f"Can I deposit savings here ({self.calls}_{i})?"},
                        {"Jamie": f"Yes, this is a [{word}]."},
                        {"Alex": "Can I open an account?"},
                        {"Jamie": "Bring identification."},
                    ],
                    completion_points=[dict(turn_index=2, distractors=wrong)],
                )
            else:
                payload = dict(
                    source=f"They put money in an institution ({self.calls}_{i}).",
                    correct=f"They deposited money at the [{word}].",
                    distractors=[f"The [{word}] grows {w}." for w in wrong],
                )
            output.append(payload)
        return dict(artifacts=output)


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


async def save_settings(sessions, user):
    async with sessions() as session, session.begin():
        (await session.get(User, user.id)).settings = user.settings


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


@pytest.mark.parametrize("target", ["harbor", "quay", "jetty"])
async def test_browser_provider_generates_with_current_native_inventory(
    dictionary, reference, config, target
):
    import sqlite3

    from tests.system.test_web_e2e import BrowserLexicalCompletion

    lexicon, _ = dictionary
    with sqlite3.connect(reference) as connection:
        connection.execute("INSERT INTO words VALUES(42,?,?, 'word','done')", (target, target))
        connection.execute(
            "INSERT INTO entries(id,word_id,pos,definition,examples,entry_order) "
            "VALUES(42,42,'noun','a place for boats','[]',1)"
        )
        connection.execute(
            "INSERT INTO senses(id,entry_id,definition,sense_order) "
            "VALUES(42,42,'a place for boats',1)"
        )
    await lexicon.import_reference(reference)
    lexicon.llm = BrowserLexicalCompletion()
    manager = lexicon.test_generations
    data = GenerationRequest(reference_id=encode_reference_id(42), target=target)
    result = await manager.submit(data.target, reference_id=data.reference_id)
    await asyncio.gather(*(task for _, task in list(manager.flights.values())))
    if target == "quay":
        assert manager.status(result["task_id"])["status"] == "FAILED"
        retry = await manager.submit(data.target, reference_id=data.reference_id)
        assert retry["task_id"] != result["task_id"]
        result = retry
        await asyncio.gather(*(task for _, task in list(manager.flights.values())))
    stored = manager.status(result["task_id"])
    assert stored["status"] == "SUCCEEDED"
    assert stored["stage"] == "READY"
    word = await lexicon.get_word(stored["word_id"])
    assert word.lemma == target
    assert word.senses[0].definition.content == "a place for boats"
    assert word.senses[0].examples
    assert not hasattr(word.senses[0], "usage_note")


async def test_search_serializes_ranked_hits_and_excludes_generated_reference(
    database, dictionary, config
):
    app = create_app()
    app.state.sessions = database[1]
    app.state.product = config
    app.state.lexicon = dictionary[0]

    async def guest():
        return None

    app.dependency_overrides[optional_actor] = guest
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/v1/words:search", params={"query": "bank", "include_reference": True}
        )
        assert response.status_code == 200
        assert response.json() == {
            "items": [
                {
                    "kind": "WORD",
                    "word_id": 1,
                    "lemma": "bank",
                    "entry_type": "WORD",
                    "match_kind": "EXACT",
                    "matched_surface": "bank",
                }
            ]
        }


async def test_generation_deduplicates_relations_after_resolving_word_identity(
    database, dictionary, reference
):
    import sqlite3

    with sqlite3.connect(reference) as connection:
        connection.execute("INSERT INTO words VALUES(42,'harbor','harbor','word','done')")
        connection.execute(
            "INSERT INTO entries(id,word_id,pos,definition,examples,entry_order) "
            "VALUES(42,42,'noun','a sheltered place for ships','[]',1)"
        )
        connection.execute(
            "INSERT INTO senses(id,entry_id,definition,sense_order) "
            "VALUES(42,42,'a sheltered place for ships',1)"
        )

    class Completion:
        async def complete(self, instruction, data, schema):
            if schema.__name__ == "InventoryOutput":
                return {
                    "lemma": "harbor",
                    "type": "word",
                    "aliases": [],
                    "related": {
                        "WORD_FAMILY": ["harbour", "HARBOUR"],
                        "CONFUSED_WITH": ["harbour"],
                    },
                    "senses": [
                        {
                            "definition": "a sheltered place for ships",
                            "pos": "noun",
                            "references": ["a1"],
                        }
                    ],
                }
            return {
                "senses": [
                    {
                        "sense_id": 1,
                        "tier": "core",
                        "examples": [
                            "The ship entered the [harbor].",
                            "THE SHIP ENTERED THE [HARBOR].",
                            "Broken [harbor",
                            "Unknown [harbor|typo].",
                        ],
                        "forms": ["harbor"],
                        "patterns": [],
                        "collocations": [],
                        "relations": {},
                        "cefr_level": "B1",
                        "register": None,
                    }
                ]
            }

    lexicon = dictionary[0]
    lexicon.llm = Completion()
    engine, _, _ = database
    async with engine.begin() as connection:
        for table in ("words", "senses"):
            await connection.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('lexi.{table}', 'id'), "
                    f"(SELECT max(id) FROM lexi.{table}))"
                )
            )
    await lexicon.import_reference(reference)
    word = await lexicon.generate_word("harbor", reference_id=encode_reference_id(42))
    assert [example.content for example in word.senses[0].examples] == [
        "The ship entered the [harbor]."
    ]
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT target.lemma, relation.rel_type FROM lexi.word_relations relation "
                    "JOIN lexi.words target ON target.id=relation.to_word_id "
                    "WHERE relation.from_word_id=:word ORDER BY relation.rel_type"
                ),
                {"word": word.id},
            )
        ).all()
    assert sorted(rows) == [("harbour", "CONFUSED_WITH"), ("harbour", "WORD_FAMILY")]
    assert (
        await lexicon.generate_word("harbor", reference_id=encode_reference_id(42))
    ).id == word.id


async def test_native_enrichment_batches_run_concurrently_without_four_request_cap(
    database, dictionary, reference
):
    import sqlite3

    with sqlite3.connect(reference) as connection:
        connection.execute("INSERT INTO words VALUES(43,'jetty','jetty','word','done')")
        connection.execute(
            "INSERT INTO entries(id,word_id,pos,definition,examples,entry_order) "
            "VALUES(43,43,'noun','a place for boats','[]',1)"
        )
        connection.execute(
            "INSERT INTO senses(id,entry_id,definition,sense_order) "
            "VALUES(43,43,'a place for boats',1)"
        )

    class Completion:
        def __init__(self):
            self.inventory_done = False
            self.started = 0
            self.active = 0
            self.gate = asyncio.Event()

        async def complete(self, instruction, data, schema):
            if schema.__name__ == "InventoryOutput":
                assert self.started == 0
                self.inventory_done = True
                return {
                    "lemma": "jetty",
                    "type": "WORD",
                    "aliases": [],
                    "related": {},
                    "senses": [
                        {
                            "definition": f"boat landing meaning {i}",
                            "pos": "NOUN",
                            "references": ["a1"],
                        }
                        for i in range(33)
                    ],
                }
            assert self.inventory_done
            assert schema.__name__ == "EnrichmentBatch"
            self.started += 1
            self.active += 1
            if self.started == 5:
                self.gate.set()
            try:
                await asyncio.wait_for(self.gate.wait(), 3)
                context = json.loads(
                    data.removeprefix("<sense_request>").removesuffix("</sense_request>").strip()
                )
                assert 1 <= len(context["senses"]) <= 8
                return {
                    "senses": [
                        {
                            "sense_id": sense["sense_id"],
                            "tier": "CORE",
                            "examples": ["Boats dock at the [jetty]."],
                            "forms": [],
                            "patterns": [],
                            "collocations": [],
                            "relations": {},
                            "cefr_level": "B1",
                            "register": None,
                        }
                        for sense in context["senses"]
                    ]
                }
            finally:
                self.active -= 1

    lexicon = dictionary[0]
    lexicon.llm = llm = Completion()
    engine, _, _ = database
    async with engine.begin() as connection:
        for table in ("words", "senses"):
            await connection.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('lexi.{table}', 'id'), "
                    f"(SELECT max(id) FROM lexi.{table}))"
                )
            )
    await lexicon.import_reference(reference)
    word = await lexicon.generate_word("jetty", reference_id=encode_reference_id(43))
    assert llm.started == 5
    assert llm.active == 0
    assert len(word.senses) == 33


async def deck_and_prepare(
    database, dictionary, user, config, *, kind="DEFINITION_TO_WORD", fmt="SINGLE_CHOICE", k=2
):
    _, sessions, _ = database
    user.settings = {
        "learning": {
            "question_types": [kind],
            "formats": [fmt],
            "questions_per_sense": k,
            "max_sense_count": 1,
        }
    }
    await save_settings(sessions, user)
    async with sessions() as session:
        node = await create_node(
            session, user.id, NodeCreate(type="DECK", name="Learning", sense_ids=[1]), config
        )
    async with sessions() as session:
        prepared = await prepare(session, dictionary[0], user, node["id"], config)
    return node, prepared


def result(item, *, correct=True, diagnostics=None, answered_at=None):
    return dict(
        question_artifact_id=item.question.question_artifact_id,
        question_type=item.question.question_type,
        format=item.format,
        diagnostics=diagnostics or dict(correct=correct),
        answered_at=answered_at or datetime.now(UTC) - timedelta(seconds=1),
    )


async def test_prepare_refills_singleton_once_and_allows_repeated_public_pairs(
    database, dictionary, user, config
):
    _, prepared = await deck_and_prepare(database, dictionary, user, config, k=3)
    assert prepared["actual_question_count"] == 3
    items = prepared["bundles"][0]["questions"]
    assert len({item.question.question_artifact_id for item in items}) == 1
    assert dictionary[1].calls == 1
    assert all(item.format == "SINGLE_CHOICE" and item.level == 1 for item in items)


async def test_contextual_refill_saves_eight_but_returns_requested_runtime_count(
    database, dictionary, user, config
):
    node, prepared = await deck_and_prepare(
        database, dictionary, user, config, kind="CONTEXT_TO_WORD", k=2
    )
    assert prepared["actual_question_count"] == 2
    counts = await dictionary[0].count_question_artifacts_for_senses([1])
    assert counts[1, QuestionArtifactType.CONTEXT_TO_WORD] == 8
    async with database[1]() as session:
        repeated = await prepare(session, dictionary[0], user, node["id"], config)
    assert repeated["actual_question_count"] == 2
    assert dictionary[1].calls == 1


async def test_pro_typed_only_new_sense_uses_minimum_available_fallback(
    database, dictionary, user, config
):
    async with database[1]() as session, session.begin():
        (await session.get(User, user.id)).plan = Plan.PRO
    _, prepared = await deck_and_prepare(
        database, dictionary, user, config, kind="SENTENCE_REWRITE", fmt="SHORT_ANSWER", k=1
    )
    assert prepared["bundles"][0]["questions"][0].level == 5
    assert prepared["bundles"][0]["questions"][0].format == "SHORT_ANSWER"


async def test_duplicates_group_once_and_receipt_is_atomic_and_idempotent(
    database, dictionary, user, config
):
    _, prepared = await deck_and_prepare(database, dictionary, user, config, k=3)
    items = prepared["bundles"][0]["questions"]
    data = ReviewBatch(results=[result(item) for item in items])
    key = uuid4()
    async with database[1]() as session:
        accepted = await review(session, user.id, data, key, config)
    assert len(accepted["results"]) == 1
    assert len(accepted["evidence"]) == 3
    assert accepted["results"][0]["elo"] > 600
    async with database[1]() as session:
        assert await review(session, user.id, data, key, config) == accepted
    async with database[1]() as session:
        memory = await session.get(UserSense, (user.id, 1))
        assert memory.review_count == 1
    changed = ReviewBatch(results=[result(items[0], correct=False)])
    async with database[1]() as session:
        with pytest.raises(Problem, match="review_batch_conflict"):
            await review(session, user.id, changed, key, config)


async def test_same_time_review_has_no_elo_gain_and_older_submission_is_log_only(
    database, dictionary, user, config
):
    _, prepared = await deck_and_prepare(database, dictionary, user, config, k=1)
    item = prepared["bundles"][0]["questions"][0]
    moment = datetime.now(UTC) - timedelta(seconds=1)
    data = ReviewBatch(results=[result(item, answered_at=moment)])
    async with database[1]() as session:
        first = await review(session, user.id, data, uuid4(), config)
    async with database[1]() as session:
        repeated = await review(session, user.id, data, uuid4(), config)
    assert repeated["results"][0]["elo"] == first["results"][0]["elo"]
    async with database[1]() as session:
        older = await review(
            session,
            user.id,
            ReviewBatch(
                results=[result(item, correct=False, answered_at=moment - timedelta(days=1))]
            ),
            uuid4(),
            config,
        )
    assert older["results"][0]["applied"] is False
    assert older["results"][0]["due_after"] == repeated["results"][0]["due_after"]
    assert older["evidence"][0]["recall"] == 0


async def test_all_null_initial_review_uses_prior_and_refreshes_exposure(
    database, dictionary, user, config
):
    _, prepared = await deck_and_prepare(
        database, dictionary, user, config, kind="WORD_TO_USAGE", k=1
    )
    item = prepared["bundles"][0]["questions"][0]
    async with database[1]() as session:
        accepted = await review(
            session, user.id, ReviewBatch(results=[result(item)]), uuid4(), config
        )
    state = accepted["results"][0]
    assert (state["stability"], state["difficulty"]) == (1, 5)
    assert accepted["evidence"][0]["recall"] is None
    assert state["due_after"] > state["last_exposure_at"]


async def test_matched_other_sense_receives_credit_and_wrong_answer_penalizes_target(
    database, dictionary, user, config
):
    async with database[1]() as session, session.begin():
        (await session.get(User, user.id)).plan = Plan.PRO
    _, prepared = await deck_and_prepare(database, dictionary, user, config, fmt="SINGLE_WORD", k=1)
    item = prepared["bundles"][0]["questions"][0]
    correct = result(item, diagnostics=dict(task_fit=True, spelling_error=False, sense_id=2))
    async with database[1]() as session:
        accepted = await review(session, user.id, ReviewBatch(results=[correct]), uuid4(), config)
    assert accepted["results"][0]["sense_id"] == 2
    wrong = result(item, diagnostics=dict(task_fit=False, spelling_error=False, sense_id=2))
    async with database[1]() as session:
        rejected = await review(session, user.id, ReviewBatch(results=[wrong]), uuid4(), config)
    assert rejected["results"][0]["sense_id"] == 1
    assert rejected["results"][0]["elo"] < 600


async def test_http_typed_grading_uses_saved_artifact_and_submit_consumes_diagnostics(
    database, dictionary, user, config
):
    async with database[1]() as session, session.begin():
        (await session.get(User, user.id)).plan = Plan.PRO
    _, prepared = await deck_and_prepare(database, dictionary, user, config, fmt="SINGLE_WORD", k=1)
    item = prepared["bundles"][0]["questions"][0]
    app = create_app()
    app.state.sessions, app.state.product, app.state.lexicon = database[1], config, dictionary[0]

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        reference = dict(
            question_artifact_id=item.question.question_artifact_id,
            question_type="DEFINITION_TO_WORD",
            format="SINGLE_WORD",
        )
        graded = await client.post("/v1/study:grade", json=reference | dict(answer="bank"))
        assert graded.status_code == 200, graded.text
        assert graded.json()["diagnostics"] == dict(task_fit=True, spelling_error=False, sense_id=1)
        submitted = await client.post(
            "/v1/study:submitResults",
            headers={"Idempotency-Key": str(uuid4())},
            json=dict(
                results=[
                    graded.json()
                    | dict(answered_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
                ]
            ),
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["evidence"][0]["performance"] == 1
        for missing in ("format", "question_type"):
            incomplete = graded.json() | dict(answered_at=datetime.now(UTC).isoformat())
            del incomplete[missing]
            invalid = await client.post(
                "/v1/study:submitResults",
                headers={"Idempotency-Key": str(uuid4())},
                json={"results": [incomplete]},
            )
            assert invalid.status_code == 422, invalid.text
        assert (await client.post("/v1/study:submitReviews", json={})).status_code == 404
