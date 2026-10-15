from types import SimpleNamespace

import pytest
from sqlalchemy import delete, event, func, select

from pycil.app.config import load_config
from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import append
from pycil.study.enums import ALLOWED_PAIRS, QuestionType, ResponseFormat
from pycil.study.enums import QuestionArtifactType as Kind
from pycil.study.errors import QuestionArtifactNotFoundError, UnsupportedQuestionFormatError
from pycil.study.grading import grade_answer
from pycil.study.models import ReviewReceipt, UserSense
from pycil.vocabulary.enums import EntryType, GenerationState, PartOfSpeech, Tier
from pycil.vocabulary.errors import InvalidOutputError, InvalidResourceError
from pycil.vocabulary.models import Definition, Sense, Word
from pycil.vocabulary.search import SearchIndex
from tests.support.artifacts import payloads
from tests.support.vocabulary import neutral_word


class Decision:
    def __init__(self, answers):
        self.answers = iter(answers)

    async def decide(self, schema, context):
        choices, nouls = next(self.answers)
        return SimpleNamespace(**choices, **nouls)


@pytest.mark.parametrize(
    "answer, task_fit, spelling_error",
    [("lender", True, False), ("lenderr", True, True), ("lender", False, False)],
)
async def test_single_word_grading_resolves_alternate_meaning_through_real_search(
    database, answer, task_fit, spelling_error
):
    _, target_id = await neutral_word(database.sessions)
    async with database.sessions() as session, session.begin():
        word = Word(
            lemma="lender",
            match_key="lender",
            entry_type=EntryType.WORD,
            generation_state=GenerationState.DONE,
        )
        session.add(word)
        await session.flush()
        alternate = Sense(word_id=word.id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(alternate)
        await session.flush()
        session.add(
            Definition(sense_id=alternate.id, theme_id=None, content="a person who lends money")
        )
    saved = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=target_id,
                theme_id=None,
                artifact_type=Kind.CONTEXT_TO_WORD,
                payload=payloads()[Kind.CONTEXT_TO_WORD],
            )
        ],
    )
    index = SearchIndex(database.sessions)
    try:
        await index.start()
        result = await grade_answer(
            database.sessions,
            index,
            Decision(
                [
                    ({}, {"task_fit": float(task_fit), "spelling_error": float(spelling_error)}),
                    ({"matched_sense": f"sense_{alternate.id}"}, {}),
                ]
            ),
            None,
            saved[0].id,
            QuestionType.CONTEXT_TO_WORD,
            ResponseFormat.SINGLE_WORD,
            answer,
            load_config().runtime.providers.vocabulary,
            allowed_pairs=ALLOWED_PAIRS,
        )
        assert result.model_dump() == dict(
            task_fit=task_fit, spelling_error=spelling_error, sense_id=alternate.id
        )
    finally:
        await index.close()


@pytest.mark.parametrize(
    "kind, bank, fmt",
    [
        (QuestionType.DEFINITION_TO_WORD, Kind.WORD_DEFINITION, ResponseFormat.SINGLE_WORD),
        (QuestionType.WORD_TO_DEFINITION, Kind.WORD_DEFINITION, ResponseFormat.SHORT_ANSWER),
        (QuestionType.WORD_TO_USAGE, Kind.WORD_TO_USAGE, ResponseFormat.SHORT_ANSWER),
        (QuestionType.SENTENCE_REWRITE, Kind.SENTENCE_REWRITE, ResponseFormat.SHORT_ANSWER),
    ],
)
async def test_null_answer_returns_unused_diagnostics_without_inference(database, kind, bank, fmt):
    _, sense_id = await neutral_word(database.sessions)
    saved = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=bank,
                payload=payloads()[bank],
            )
        ],
    )
    result = await grade_answer(
        database.sessions,
        None,
        Decision([]),
        None,
        saved[0].id,
        kind,
        fmt,
        None,
        load_config().runtime.providers.vocabulary,
        allowed_pairs=ALLOWED_PAIRS,
    )
    if fmt is ResponseFormat.SINGLE_WORD:
        expected = {"task_fit": False, "spelling_error": False, "sense_id": None}
    elif kind is QuestionType.WORD_TO_DEFINITION:
        expected = {"sense_id": None, "accuracy": None, "coverage": None}
    else:
        expected = {
            "used": False,
            "meaning": None,
            "form": None,
            "construction": None,
            "collocation": None,
            "appropriacy": None,
        }
        if kind is QuestionType.SENTENCE_REWRITE:
            expected["meaning_preservation"] = None
    assert result.model_dump() == expected


@pytest.mark.parametrize(
    "kind, bank, answers, expected",
    [
        (
            QuestionType.WORD_TO_DEFINITION,
            Kind.WORD_DEFINITION,
            [({"defined_meaning": "no_candidate"}, {})],
            {"sense_id": None, "accuracy": None, "coverage": None},
        ),
        (QuestionType.WORD_TO_USAGE, Kind.WORD_TO_USAGE, [({}, {"used": 0.1})], {"used": False}),
        (
            QuestionType.WORD_TO_USAGE,
            Kind.WORD_TO_USAGE,
            [
                ({}, {"used": 0.9}),
                (
                    {"meaning": "approximate", "form": "spelling_error"},
                    {"construction": 0.8, "collocation": 0.1, "appropriacy": 0.9},
                ),
            ],
            {
                "used": True,
                "meaning": "approximate",
                "form": "spelling_error",
                "construction": True,
                "collocation": False,
                "appropriacy": True,
            },
        ),
        (
            QuestionType.SENTENCE_REWRITE,
            Kind.SENTENCE_REWRITE,
            [
                ({}, {"used": 0.9}),
                (
                    {"meaning": "correct", "form": "correct", "meaning_preservation": "partial"},
                    {"construction": 0.9, "collocation": 0.9, "appropriacy": 0.9},
                ),
            ],
            {"used": True, "meaning_preservation": "partial"},
        ),
    ],
)
async def test_semantic_grading_branches_are_readonly(database, kind, bank, answers, expected):
    _, sense_id = await neutral_word(database.sessions)
    saved = await append(
        database.sessions,
        [
            Artifact(
                id=0, sense_id=sense_id, theme_id=None, artifact_type=bank, payload=payloads()[bank]
            )
        ],
    )
    statements = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].lower())

    event.listen(database.engine.sync_engine, "before_cursor_execute", observe)
    try:
        result = await grade_answer(
            database.sessions,
            None,
            Decision(answers),
            None,
            saved[0].id,
            kind,
            ResponseFormat.SHORT_ANSWER,
            "The bank opens.",
            load_config().runtime.providers.vocabulary,
            allowed_pairs=ALLOWED_PAIRS,
        )
        assert result.model_dump(mode="json").items() >= expected.items()
        assert statements and set(statements) == {"select"}
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", observe)


async def test_out_of_inventory_decision_is_rejected_without_credit(database):
    _, sense_id = await neutral_word(database.sessions)
    saved = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=Kind.WORD_DEFINITION,
                payload=payloads()[Kind.WORD_DEFINITION],
            )
        ],
    )
    with pytest.raises(InvalidOutputError, match="unavailable meaning"):
        await grade_answer(
            database.sessions,
            None,
            Decision([({"defined_meaning": "sense_999"}, {})]),
            None,
            saved[0].id,
            QuestionType.WORD_TO_DEFINITION,
            ResponseFormat.SHORT_ANSWER,
            "meaning",
            load_config().runtime.providers.vocabulary,
            allowed_pairs=ALLOWED_PAIRS,
        )


@pytest.mark.parametrize(
    "failure", ["missing", "wrong_type", "choice_format", "missing_meaning", "provider"]
)
async def test_grading_failures_do_not_publish_content_or_learning_state(database, failure):
    _, sense_id = await neutral_word(database.sessions)
    saved = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=Kind.WORD_DEFINITION,
                payload=payloads()[Kind.WORD_DEFINITION],
            )
        ],
    )
    artifact_id, kind, fmt = (
        saved[0].id,
        QuestionType.WORD_TO_DEFINITION,
        ResponseFormat.SHORT_ANSWER,
    )
    expected = InvalidOutputError
    if failure == "missing":
        artifact_id, expected = saved[0].id + 100, QuestionArtifactNotFoundError
    elif failure == "wrong_type":
        kind, expected = QuestionType.WORD_TO_USAGE, UnsupportedQuestionFormatError
    elif failure == "choice_format":
        fmt, expected = ResponseFormat.SINGLE_CHOICE, UnsupportedQuestionFormatError
    elif failure == "missing_meaning":
        async with database.sessions() as session, session.begin():
            await session.execute(delete(Definition).where(Definition.sense_id == sense_id))
        expected = InvalidResourceError

    class FailedProvider:
        async def decide(self, *args, **kwargs):
            raise InvalidOutputError("provider output was unusable")

    # Only the provider-error scenario may reach the remote boundary.
    decision_llm = FailedProvider() if failure == "provider" else Decision([])
    async with database.sessions() as session:
        before = await session.scalar(select(func.count()).select_from(Definition))
    with pytest.raises(expected):
        await grade_answer(
            database.sessions,
            None,
            decision_llm,
            None,
            artifact_id,
            kind,
            fmt,
            "a financial institution",
            load_config().runtime.providers.vocabulary,
            allowed_pairs=ALLOWED_PAIRS,
        )
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(UserSense)) == 0
        assert await session.scalar(select(func.count()).select_from(ReviewReceipt)) == 0
        assert await session.scalar(select(func.count()).select_from(Definition)) == before
