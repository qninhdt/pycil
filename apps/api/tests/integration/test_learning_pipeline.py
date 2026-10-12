import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from lexi_ai import QuestionArtifactType
from lexi_ai.references.cambridge import encode_reference_id
from sqlalchemy import text

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


async def save_settings(sessions, user):
    async with sessions() as session, session.begin():
        (await session.get(User, user.id)).settings = user.settings


@pytest.mark.parametrize("target", ["harbor", "quay", "jetty"])
async def test_browser_provider_generates_with_current_native_inventory(
    dictionary, reference, config, target
):
    import sqlite3

    from tests.support.inference import BrowserLexicalCompletion

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


@pytest.mark.parametrize("failure", ["bad_request", "connection", "timeout"])
async def test_cold_preparation_provider_failure_is_retryable_without_learning_writes(
    database, dictionary, user, config, monkeypatch, failure
):
    from openai import APIConnectionError, APITimeoutError, BadRequestError

    request = httpx.Request("POST", "https://provider.invalid/completions")
    errors = {
        "bad_request": BadRequestError(
            "provider rejected the request",
            response=httpx.Response(400, request=request),
            body=None,
        ),
        "connection": APIConnectionError(request=request),
        "timeout": APITimeoutError(request=request),
    }
    user.settings = {
        "learning": {
            "question_types": ["DEFINITION_TO_WORD"],
            "formats": ["SINGLE_CHOICE"],
            "questions_per_sense": 1,
            "max_sense_count": 1,
        }
    }
    await save_settings(database[1], user)
    async with database[1]() as session:
        node = await create_node(
            session, user.id, NodeCreate(type="DECK", name="Cold bank", sense_ids=[1]), config
        )
    native = dictionary[0].llm.complete

    async def unavailable(*args, **kwargs):
        raise errors[failure]

    monkeypatch.setattr(dictionary[0].llm, "complete", unavailable)
    app = create_app()
    app.state.sessions, app.state.product, app.state.lexicon = database[1], config, dictionary[0]

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        body = {"node_id": str(node["id"]), "selection": "NEW"}
        failed = await client.post("/v1/study:prepare", json=body)
        assert failed.status_code == 503
        assert failed.json() == {"error": "question_generation_unavailable"}
        counts = await client.get("/v1/study/progress", params={"node_id": str(node["id"])})
        assert counts.json()["studied"] == 0
        monkeypatch.setattr(dictionary[0].llm, "complete", native)
        ready = await client.post("/v1/study:prepare", json=body)
        assert ready.status_code == 200, ready.text
        assert ready.json()["actual_question_count"] == 1


@pytest.mark.parametrize("provider", ["inference", "decision"])
async def test_typed_grading_provider_transport_errors_preserve_retryable_contract(
    database, dictionary, user, config, monkeypatch, provider
):
    from openai import APIConnectionError
    from typesafe_sdk import TypeSafeAPIError

    async with database[1]() as session, session.begin():
        (await session.get(User, user.id)).plan = Plan.PRO
    _, prepared = await deck_and_prepare(database, dictionary, user, config, fmt="SINGLE_WORD", k=1)
    item = prepared["bundles"][0]["questions"][0]
    error = (
        APIConnectionError(request=httpx.Request("POST", "https://provider.invalid/completions"))
        if provider == "inference"
        else TypeSafeAPIError(503, None, {})
    )

    async def unavailable(*args, **kwargs):
        raise error

    decision = dictionary[0]._decision_model()
    monkeypatch.setattr(decision, "decide", unavailable)
    app = create_app()
    app.state.sessions, app.state.product, app.state.lexicon = database[1], config, dictionary[0]

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        failed = await client.post(
            "/v1/study:grade",
            json={
                "question_artifact_id": item.question.question_artifact_id,
                "question_type": "DEFINITION_TO_WORD",
                "format": "SINGLE_WORD",
                "answer": "unrelated answer",
            },
        )
        assert failed.status_code == 503
        assert failed.json() == {"error": "grading_unavailable"}


async def test_http_prepare_empty_new_due_scope_and_saved_maximum(
    database, dictionary, user, config
):
    user.settings = {"learning": {"max_sense_count": 1, "questions_per_sense": 1}}
    await save_settings(database[1], user)
    async with database[1]() as session:
        empty = await create_node(session, user.id, NodeCreate(type="DECK", name="empty"), config)
        deck = await create_node(
            session, user.id, NodeCreate(type="DECK", name="new", sense_ids=[1, 2]), config
        )
    app = create_app()
    app.state.sessions, app.state.product, app.state.lexicon = database[1], config, dictionary[0]

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        nothing = await client.post(
            "/v1/study:prepare", json={"node_id": str(empty["id"]), "selection": "AUTO"}
        )
        assert nothing.status_code == 200 and nothing.json()["bundles"] == []
        prepared = await client.post(
            "/v1/study:prepare", json={"node_id": str(deck["id"]), "selection": "NEW"}
        )
        assert prepared.status_code == 200
        assert prepared.json()["actual_sense_count"] == 1
        assert all(
            bundle["reason"] == "NEW" and bundle["sense"]["id"] in [1, 2]
            for bundle in prepared.json()["bundles"]
        )
        due = await client.post(
            "/v1/study:prepare", json={"node_id": str(deck["id"]), "selection": "DUE"}
        )
        assert due.status_code == 200 and due.json()["bundles"] == []
        missing = await client.post(
            "/v1/study:prepare", json={"node_id": str(uuid4()), "selection": "AUTO"}
        )
        assert missing.status_code == 404 and missing.json() == {"error": "node_not_found"}
        progress = await client.get("/v1/study/progress", params={"node_id": str(deck["id"])})
        assert progress.json()["new"] == 2 and progress.json()["studied"] == 0
