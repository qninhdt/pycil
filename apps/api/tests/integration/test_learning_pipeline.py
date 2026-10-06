import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from lexi_ai import Lexicon, QuestionType, ResponseFormat
from lexi_ai.references.cambridge import encode_available_id
from sqlalchemy import event, func, select, text

from pycil.account.auth import actor, optional_actor
from pycil.account.models import UsageEvent
from pycil.account.plans import Plan
from pycil.account.usage import change_plan
from pycil.http import Problem
from pycil.library.nodes import create_node
from pycil.library.schemas import NodeCreate
from pycil.main import create_app
from pycil.study.models import Rating, ReviewLog, SenseMemory
from pycil.study.preparation import prepare
from pycil.study.reviews import review
from pycil.study.schemas import Review
from pycil.vocabulary.api import GenerationRequest
from pycil.vocabulary.generation import claim, coverage, execute, recover, submit
from pycil.vocabulary.models import GenerationStatus, WordGeneration
from pycil.worker import ownership


class LocalCompletion:
    """Deterministic external completion. Native validation/generation/storage stay real."""

    def __init__(self):
        self.calls = 0

    async def complete(self, instruction, data, schema):
        self.calls += 1
        context = json.loads(
            data.removeprefix("<question_context>").removesuffix("</question_context>").strip()
        )
        kind = QuestionType(context["question_type"])
        word, definition = context["word"], context["definition"]
        output = []
        for i in range(context["count"]):
            content = {
                QuestionType.DEFINITION_TO_WORD: definition,
                QuestionType.CONTEXT_TO_WORD: f"What holds savings? ({i})",
                QuestionType.CLOZE_TO_WORD: f"I visit the _ today ({i}).",
                QuestionType.WORD_TO_DEFINITION: f'<t inf="base">{word}</t>',
                QuestionType.WORD_TO_USAGE: f'<t inf="base">{word}</t> — {definition}',
                QuestionType.MEANING_IN_CONTEXT: (
                    f'I visit the <t inf="base">{word}</t> today ({i}).'
                ),
                QuestionType.DIALOGUE_COMPLETION: [
                    {"speaker": "Alex", "text": f'Going to the <t inf="base">{word}</t>? ({i})'},
                    {"speaker": "Jamie", "text": None},
                ],
            }[kind]
            item = {
                "content": content,
                "distractors": [
                    {"content": option, "explanation": "Another meaning"}
                    for option in ("tree", "meal", "car")
                ],
            }
            if schema.__name__ == "AnchoredQuestionBatch":
                item["correct_explanation"] = "Saved meaning"
            else:
                item["correct"] = {"content": word, "explanation": "Saved meaning"}
            output.append(item)
        return {"questions": output}


@pytest.fixture
async def dictionary(database, reference, senses):
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
            text("INSERT INTO lexi.word_sources(word_id,source_id) VALUES(1,1)")
        )
    llm = LocalCompletion()
    value = Lexicon(db_url=url, db_schema="lexi", cambridge_path=str(reference), llm=llm)
    try:
        yield value, llm
    finally:
        await value.close()


async def fill(database, dictionary, config):
    engine, sessions, _ = database
    lexicon, _ = dictionary
    data = GenerationRequest(available_id=encode_available_id(1), target="bank")
    results = await asyncio.gather(*(submit(sessions, lexicon, data, config) for _ in range(3)))
    assert len({r["generation_id"] for r in results}) == 1
    async with ownership(engine) as ensure_owner:
        row = await claim(sessions, config)
        await execute(sessions, lexicon, row, config, ensure_owner)
    return results[0]["generation_id"]


async def test_native_generation_bank_reuse_and_singleton(database, dictionary, config):
    engine, sessions, _ = database
    identifier = await fill(database, dictionary, config)
    lexicon, llm = dictionary
    counts = await coverage(lexicon, [1, 2], config)
    assert all(counts[s, kind] == 8 for s in [1, 2] for kind in QuestionType)
    async with sessions() as session:
        row = await session.get(WordGeneration, identifier)
        assert row.status is GenerationStatus.SUCCEEDED
        assert row.id.version == 7
        assert row.word_id == 1
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 0
    calls = llm.calls
    await submit(
        sessions,
        lexicon,
        GenerationRequest(available_id=encode_available_id(1), target="bank"),
        config,
    )
    assert llm.calls == calls
    async with ownership(engine):
        with pytest.raises(RuntimeError, match="already_running"):
            async with ownership(engine):
                pytest.fail("only one worker")


async def test_exhausted_running_recovery_is_failed(database, dictionary, config):
    _, sessions, _ = database
    data = GenerationRequest(available_id=encode_available_id(1), target="bank")
    identifier = (await submit(sessions, dictionary[0], data, config))["generation_id"]
    async with sessions() as session, session.begin():
        row = await session.get(WordGeneration, identifier)
        row.status, row.attempts = GenerationStatus.RUNNING, config.generation.worker.max_attempts
    await recover(sessions, config)
    async with sessions() as session:
        assert (await session.get(WordGeneration, identifier)).status is GenerationStatus.FAILED


async def test_append_before_status_crash_recovery_fills_only_missing_without_search(
    database,
    dictionary,
    config,
    monkeypatch,
):
    from lexi_ai import Lexicon

    engine, sessions, _ = database
    lexicon, llm = dictionary
    identifier = (
        await submit(
            sessions,
            lexicon,
            GenerationRequest(
                available_id=encode_available_id(1),
                target="bank",
            ),
            config,
        )
    )["generation_id"]

    async def no_search(*args, **kwargs):
        pytest.fail("selected generation must not search")

    monkeypatch.setattr(Lexicon, "search", no_search)
    original = Lexicon.generate_questions

    async def crash_after_save(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        raise asyncio.CancelledError

    monkeypatch.setattr(Lexicon, "generate_questions", crash_after_save)
    async with ownership(engine) as ensure_owner:
        row = await claim(sessions, config)
        with pytest.raises(asyncio.CancelledError):
            await execute(sessions, lexicon, row, config, ensure_owner)
    assert llm.calls == 1
    async with sessions() as session:
        assert (await session.get(WordGeneration, identifier)).status is GenerationStatus.RUNNING
    monkeypatch.setattr(Lexicon, "generate_questions", original)
    async with ownership(engine) as ensure_owner:
        await recover(sessions, config)
        row = await claim(sessions, config)
        assert row.attempts == 2
        await execute(sessions, lexicon, row, config, ensure_owner)
    counts = await coverage(lexicon, [1, 2], config)
    assert all(counts[s, kind] == 8 for s in [1, 2] for kind in QuestionType)
    assert llm.calls == 14
    async with sessions() as session:
        assert (await session.get(WordGeneration, identifier)).status is GenerationStatus.SUCCEEDED
        assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 0


async def test_preparation_priority_small_unready_scope_and_nonmultiple_budget(
    database,
    dictionary,
    user,
    config,
):
    _, sessions, _ = database
    await fill(database, dictionary, config)
    async with sessions() as session:
        node = await create_node(
            session, user.id, NodeCreate(type="DECK", name="learn", sense_ids=[1, 2]), config
        )
    async with sessions() as session:
        await review(session, user.id, Review(sense_id=2, rating=Rating.GOOD), uuid4(), config)
    user.settings = {"learning": {"questions_per_sense": 1, "question_budget": 2}}
    async with sessions() as session:
        result = await prepare(session, dictionary[0], user, node["id"], config)
        assert [b["reason"] for b in result["bundles"]] == ["NEW", "NOT_YET_DUE"]
    async with sessions() as session, session.begin():
        memory = await session.get(SenseMemory, (user.id, 2))
        memory.due_at = datetime.now(UTC) - timedelta(seconds=1)
    async with sessions() as session:
        result = await prepare(session, dictionary[0], user, node["id"], config)
        assert [b["sense"].id for b in result["bundles"]] == [2, 1]
        assert [b["reason"] for b in result["bundles"]] == ["DUE", "NEW"]
    user.settings = {"learning": {"questions_per_sense": 7, "question_budget": 15}}
    async with sessions() as session:
        result = await prepare(session, dictionary[0], user, node["id"], config)
        assert result["actual_question_count"] == 14
    # K counts distinct Question IDs, not distinct Question types.
    async with sessions() as session, session.begin():
        await session.execute(
            text("DELETE FROM lexi.questions WHERE sense_id=2 AND question_type='WORD_TO_USAGE'")
        )
    async with sessions() as session:
        result = await prepare(session, dictionary[0], user, node["id"], config)
        assert result["actual_sense_count"] == 2
        assert result["actual_question_count"] == 14
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                "DELETE FROM lexi.questions WHERE sense_id=2 AND id NOT IN "
                "(SELECT id FROM lexi.questions WHERE sense_id=2 ORDER BY id LIMIT 6)"
            )
        )
    async with sessions() as session:
        result = await prepare(session, dictionary[0], user, node["id"], config)
        assert result["actual_sense_count"] == 1
        assert result["actual_question_count"] == 7
        assert result["bundles"][0]["sense"].id == 1
    async with sessions() as session:
        empty = await create_node(session, user.id, NodeCreate(type="DECK", name="empty"), config)
    async with sessions() as session:
        assert (await prepare(session, dictionary[0], user, empty["id"], config))["bundles"] == []


async def test_readonly_preparation_and_typed_only_feasibility(
    database, dictionary, user, config, monkeypatch
):
    _, sessions, _ = database
    await fill(database, dictionary, config)
    async with sessions() as session:
        node = await create_node(
            session, user.id, NodeCreate(type="DECK", name="learn", sense_ids=[1, 2]), config
        )
    lexicon = dictionary[0]
    original = lexicon.retrieve_questions
    calls = []

    async def retrieve(requests):
        calls.append(requests)
        assert len({(s, t) for s, t, _ in requests}) == len(requests)
        assert all(sum(n for s, _, n in requests if s == sense_id) == 3 for sense_id in [1, 2])
        return await original(requests)

    async def forbidden(*args, **kwargs):
        pytest.fail("Preparation must use one native batch, not ID hydration or single retrieval")

    monkeypatch.setattr(lexicon, "retrieve_questions", retrieve)
    monkeypatch.setattr(lexicon, "retrieve_question", forbidden)
    monkeypatch.setattr(lexicon, "get_questions", forbidden)
    async with sessions() as session:
        result = await prepare(session, dictionary[0], user, node["id"], config)
        assert (result["actual_sense_count"], result["actual_question_count"]) == (2, 6)
        assert all(len({q["question"].id for q in b["questions"]}) == 3 for b in result["bundles"])
        assert all(type(q["level"]) is int for b in result["bundles"] for q in b["questions"])
        assert await session.scalar(select(func.count()).select_from(SenseMemory)) == 0
        assert await session.scalar(select(func.count()).select_from(ReviewLog)) == 0
    assert len(calls) == 1
    user.plan = Plan.PRO
    async with sessions() as session:
        await change_plan(session, user.id, Plan.PRO, config, datetime.now(UTC))
    user.settings = {
        "learning": {
            "question_types": ["DEFINITION_TO_WORD"],
            "formats": ["SINGLE_WORD"],
            "questions_per_sense": 3,
        }
    }
    async with sessions() as session:
        result = await prepare(session, dictionary[0], user, node["id"], config)
        assert all(
            q["format"].value == "SINGLE_WORD" for b in result["bundles"] for q in b["questions"]
        )
        assert result["actual_question_count"] == 6
        assert all(len({q["question"].id for q in b["questions"]}) == 3 for b in result["bundles"])
    assert len(calls) == 2
    assert all(t is QuestionType.DEFINITION_TO_WORD and n == 3 for _, t, n in calls[-1])
    from lexi_ai.errors import QuestionBankChangedError

    async def changed(requests):
        raise QuestionBankChangedError("Bank changed after allocation")

    monkeypatch.setattr(lexicon, "retrieve_questions", changed)
    async with sessions() as session:
        with pytest.raises(Problem, match="learning_content_changed"):
            await prepare(session, lexicon, user, node["id"], config)
    # A cached/detached PRO actor cannot retain typed learning access after downgrade.
    async with sessions() as session:
        await change_plan(session, user.id, Plan.FREE, config, datetime.now(UTC))
    async with sessions() as session:
        with pytest.raises(Problem, match="infeasible_learning_preferences"):
            await prepare(session, lexicon, user, node["id"], config)


@pytest.mark.parametrize("state", ["new", "due", "early"])
@pytest.mark.parametrize("rating", list(Rating))
async def test_exact_review_eligibility_and_practice_immutability(
    database, user, senses, config, state, rating
):
    _, sessions, _ = database
    before = None
    if state != "new":
        async with sessions() as session, session.begin():
            now = datetime.now(UTC)
            memory = SenseMemory(
                user_id=user.id,
                sense_id=1,
                stability=10,
                difficulty=5,
                last_review_at=now - timedelta(days=2),
                due_at=now + timedelta(days=1 if state == "early" else -1),
                last_rating=Rating.GOOD,
                review_count=4,
                lapse_count=1,
            )
            session.add(memory)
            await session.flush()
            from pycil.account.lifecycle import row_data

            before = row_data(memory)
    async with sessions() as session:
        response = await review(
            session, user.id, Review(sense_id=1, rating=rating), uuid4(), config
        )
    expected = state != "early" or rating is Rating.AGAIN
    assert response["applied"] is expected
    async with sessions() as session:
        memory = await session.get(SenseMemory, (user.id, 1))
        if not expected:
            from pycil.account.lifecycle import row_data

            assert row_data(memory) == before
        else:
            assert memory.review_count == (1 if state == "new" else 5)
            assert memory.lapse_count == (0 if state == "new" else 1 + int(rating is Rating.AGAIN))


async def test_review_retry_interleaving_cross_sense_conflict_and_concurrency(
    database, user, senses, config
):
    _, sessions, _ = database
    key, data = uuid4(), Review(sense_id=1, rating=Rating.GOOD)
    async with sessions() as session:
        first = await review(session, user.id, data, key, config)
    async with sessions() as session:
        await review(session, user.id, Review(sense_id=1, rating=Rating.AGAIN), uuid4(), config)
        assert await review(session, user.id, data, key, config) == first
        with pytest.raises(Problem, match="review_event_conflict"):
            await review(session, user.id, Review(sense_id=2, rating=Rating.GOOD), key, config)

    async def submit_review():
        async with sessions() as session:
            return await review(
                session, user.id, Review(sense_id=2, rating=Rating.GOOD), uuid4(), config
            )

    responses = await asyncio.gather(submit_review(), submit_review())
    assert sorted(r["applied"] for r in responses) == [False, True]


async def test_due_equality_same_day_repeat_and_zero_native_calls_for_practice(
    database,
    user,
    senses,
    config,
    monkeypatch,
):
    from pycil.study import reviews

    _, sessions, _ = database
    now = datetime(2026, 10, 2, 12, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(reviews, "datetime", Clock)
    async with sessions() as session, session.begin():
        session.add(
            SenseMemory(
                user_id=user.id,
                sense_id=1,
                stability=10,
                difficulty=5,
                last_review_at=now - timedelta(days=1),
                due_at=now,
                last_rating=Rating.GOOD,
                review_count=1,
                lapse_count=0,
            )
        )
    async with sessions() as session:
        first = await review(
            session, user.id, Review(sense_id=1, rating=Rating.GOOD), uuid4(), config
        )
        assert first["applied"]
    async with sessions() as session, session.begin():
        (await session.get(SenseMemory, (user.id, 1))).due_at = now
    async with sessions() as session:
        second = await review(
            session, user.id, Review(sense_id=1, rating=Rating.GOOD), uuid4(), config
        )
        assert second["applied"] and second["accepted_at"] == first["accepted_at"]

    def forbidden(*args):
        pytest.fail("early positive practice must not call native FSRS")

    monkeypatch.setattr(reviews, "next_state", forbidden)
    async with sessions() as session:
        event = await review(
            session, user.id, Review(sense_id=1, rating=Rating.HARD), uuid4(), config
        )
        assert not event["applied"]


async def test_concurrent_identical_key_commits_one_event(database, user, senses, config):
    _, sessions, _ = database
    key = uuid4()

    async def send():
        async with sessions() as session:
            return await review(
                session, user.id, Review(sense_id=1, rating=Rating.AGAIN), key, config
            )

    first, second = await asyncio.gather(send(), send())
    assert first == second
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ReviewLog)) == 1
        memory = await session.get(SenseMemory, (user.id, 1))
        assert memory.review_count == 1 and memory.lapse_count == 0


async def test_http_search_selected_generation_prepare_native_grade_and_rating(
    database,
    dictionary,
    user,
    config,
    monkeypatch,
):
    from types import SimpleNamespace

    from typesafe_sdk import Choice

    engine, sessions, _ = database
    lexicon, llm = dictionary

    class DiagnosticProvider:
        async def decide(self, state, questions, **options):
            return SimpleNamespace(
                choices={
                    name: SimpleNamespace(choice="no_candidate")
                    for name, q in questions.items()
                    if isinstance(q, Choice)
                },
                nouls={
                    name: SimpleNamespace(noul=0.1)
                    for name in questions
                    if name
                    in {
                        "task_fit",
                        "spelling_error",
                        "used",
                    }
                },
            )

        async def close(self):
            pass

    lexicon.decision_model = DiagnosticProvider()
    # Simulate a client selection before the source's generated Word is published.
    # Restore its native mapping before the worker so generation reuses saved Word
    # data; no synthetic completion pretends to implement Lexi Word generation.
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM lexi.word_sources WHERE word_id=1"))
    app = create_app()
    app.state.sessions, app.state.product, app.state.lexicon = sessions, config, lexicon

    async def authenticated():
        return user

    app.dependency_overrides[actor] = authenticated
    app.dependency_overrides[optional_actor] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        found = await client.get(
            "/v1/words/search", params={"query": "bank", "include_available": True}
        )
        assert found.status_code == 200
        available = found.json()["available"][0]
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO lexi.word_sources(word_id,source_id) VALUES(1,1)")
            )
        queued = await client.post(
            "/v1/word-generations",
            json={
                "available_id": available["available_id"],
                "target": "bank",
            },
        )
        assert queued.status_code == 202
        async with ownership(engine) as ensure_owner:
            row = await claim(sessions, config)
            await execute(sessions, lexicon, row, config, ensure_owner)
        status = await client.get(queued.json()["status_url"])
        assert status.json()["status"] == "SUCCEEDED"
        word = await client.get("/v1/words/1")
        assert word.status_code == 200 and len(word.json()["senses"]) == 2
        created = await client.post(
            "/v1/nodes", json={"type": "DECK", "name": "learn", "sense_ids": [1, 2]}
        )
        assert created.status_code == 201, created.text
        deck = created.json()
        assert deck["sense_ids"] == [1, 2]
        saved = await client.put(
            f"/v1/nodes/{deck['id']}",
            json={"name": "edited", "sense_ids": [1, 2]},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["sense_ids"] == [1, 2] and saved.json()["name"] == "edited"
        folder = await client.post("/v1/nodes", json={"type": "FOLDER", "name": "folder"})
        assert folder.status_code == 201 and "sense_ids" not in folder.json()
        folder_detail = await client.get(f"/v1/nodes/{folder.json()['id']}")
        assert folder_detail.status_code == 200 and "sense_count" not in folder_detail.json()
        assert "senses" not in folder_detail.json()
        listing = await client.get("/v1/nodes")
        assert listing.status_code == 200 and len(listing.json()["nodes"]) == 2
        deck_senses = await client.get(f"/v1/nodes/{deck['id']}/senses")
        assert deck_senses.status_code == 200, deck_senses.text
        assert len(deck_senses.json()["senses"]) == 2
        assert deck_senses.json()["next_after_id"] is None
        deck_detail = await client.get(f"/v1/nodes/{deck['id']}")
        assert "senses" not in deck_detail.json()
        assert "sense_page" not in deck_detail.json()
        prepared = await client.post("/v1/study/prepare", json={"node_id": str(deck["id"])})
        assert prepared.status_code == 200
        assert prepared.json()["actual_question_count"] == 6
        questions = await lexicon.list_questions_for_senses(
            [1], list(QuestionType), limit_per_type=1
        )
        kinds = {q.question_type: q for q in questions}
        word_q = kinds[QuestionType.DEFINITION_TO_WORD]
        assert (
            await client.post(
                "/v1/study/grade",
                json={
                    "question_id": word_q.id,
                    "format": "SINGLE_WORD",
                    "answer": "bank",
                },
            )
        ).status_code == 403
        user.plan = Plan.PRO
        async with sessions() as session:
            await change_plan(session, user.id, Plan.PRO, config, datetime.now(UTC))

        async def no_pre_read(*args, **kwargs):
            pytest.fail("Pycil must not pre-read the Question before native grading")

        monkeypatch.setattr(lexicon, "get_question", no_pre_read)
        reads = []

        def capture(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().startswith("SELECT"):
                reads.append(statement)

        event.listen(lexicon.db.engine.sync_engine, "before_cursor_execute", capture)
        try:
            result = await client.post(
                "/v1/study/grade",
                json={"question_id": word_q.id, "format": "SINGLE_WORD", "answer": "bank"},
            )
            assert result.status_code == 200, result.text
            assert reads == []  # Listing/preparation already warmed the native artifact.
            lexicon.db.question_cache.clear()
            result = await client.post(
                "/v1/study/grade",
                json={"question_id": word_q.id, "format": "SINGLE_WORD", "answer": "bank"},
            )
            assert result.status_code == 200, result.text
            assert len(reads) == 1  # Cold native grading reads once, with no Pycil pre-read.
        finally:
            event.remove(lexicon.db.engine.sync_engine, "before_cursor_execute", capture)

        restricted = config.model_copy(
            update={
                "learning": config.learning.model_copy(
                    update={
                        "pair_levels": {
                            kind: {
                                fmt: level
                                for fmt, level in formats.items()
                                if fmt is ResponseFormat.SINGLE_CHOICE
                            }
                            for kind, formats in config.learning.pair_levels.items()
                        },
                    }
                ),
            }
        )
        app.state.product = restricted
        result = await client.post(
            "/v1/study/grade",
            json={"question_id": word_q.id, "format": "SINGLE_WORD", "answer": "bank"},
        )
        assert result.status_code == 422 and result.json()["error"] == "unsupported_question_format"
        app.state.product = config
        expectations = [
            (
                QuestionType.DEFINITION_TO_WORD,
                "SINGLE_WORD",
                {"task_fit": False, "spelling_error": False, "sense_id": None},
            ),
            (
                QuestionType.WORD_TO_DEFINITION,
                "SHORT_ANSWER",
                {"sense_id": None, "accuracy": None, "coverage": None},
            ),
            (
                QuestionType.WORD_TO_USAGE,
                "SHORT_ANSWER",
                {
                    "used": False,
                    "meaning": None,
                    "form": None,
                    "construction": None,
                    "collocation": None,
                    "appropriacy": None,
                },
            ),
        ]
        for kind, fmt, expected in expectations:
            result = await client.post(
                "/v1/study/grade",
                json={
                    "question_id": kinds[kind].id,
                    "format": fmt,
                    "answer": "different answer",
                },
            )
            assert result.status_code == 200, result.text
            assert result.json() == expected
        for question_id, fmt, answer, code in (
            (999999, "SINGLE_WORD", "bank", 404),
            (word_q.id, "SHORT_ANSWER", "bank", 422),
            (word_q.id, "SINGLE_CHOICE", "bank", 422),
            (word_q.id, "SINGLE_WORD", " ", 422),
        ):
            result = await client.post(
                "/v1/study/grade",
                json={"question_id": question_id, "format": fmt, "answer": answer},
            )
            assert result.status_code == code, result.text
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(SenseMemory)) == 0
            assert await session.scalar(select(func.count()).select_from(UsageEvent)) == 0
        rated = await client.post(
            "/v1/study/reviews",
            headers={"Idempotency-Key": str(uuid4())},
            json={"sense_id": 1, "rating": "GOOD"},
        )
        assert rated.status_code == 200 and rated.json()["applied"] is True
        assert (await client.get("/v1/study/progress")).json()["summary"]["learned"] == 1
        history = await client.get("/v1/study/history")
        assert history.status_code == 200, history.text
        assert history.json()["events"][0]["sense_id"] == 1
        assert history.json()["events"][0]["mastery_after"] == rated.json()["mastery_after"]
        assert history.json()["applied_count"] == 1
        assert llm.calls == 14
