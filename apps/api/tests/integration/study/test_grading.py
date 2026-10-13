from types import SimpleNamespace

import pytest
from sqlalchemy import event

from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import append
from pycil.study.enums import (
    DefinitionAccuracy,
    DefinitionCoverage,
    QuestionArtifactType,
    QuestionType,
    ResponseFormat,
)
from pycil.study.errors import UnsupportedQuestionFormatError
from pycil.study.grading import grade_answer
from tests.support.vocabulary import neutral_word


class DefinitionDecision:
    def __init__(self, sense_id):
        self.sense_id, self.calls = sense_id, 0

    async def decide(self, schema, context):
        self.calls += 1
        if "defined_meaning" in schema.model_fields:
            return schema(defined_meaning=f"sense_{self.sense_id}")
        assert set(schema.model_fields) == {"accuracy", "coverage"}
        return schema(accuracy="accurate", coverage="sufficient")


async def test_grading_uses_existing_meanings_without_writing_learning_or_content(database):
    _word_id, sense_id = await neutral_word(database.sessions)
    artifacts = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=QuestionArtifactType.WORD_DEFINITION,
                payload={
                    "corrects": ["a financial institution"],
                    "distractors": [{"word": "shop", "definition": "a place to buy goods"}],
                },
            )
        ],
    )
    identifier = artifacts[0].id
    decision_llm = DefinitionDecision(sense_id)
    policy = SimpleNamespace(decision_threshold=0.7)
    pairs = {
        (QuestionType.DEFINITION_TO_WORD, ResponseFormat.SINGLE_WORD),
        (QuestionType.WORD_TO_DEFINITION, ResponseFormat.SHORT_ANSWER),
    }
    statements = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].lower())

    event.listen(database.engine.sync_engine, "before_cursor_execute", observe)
    try:
        exact = await grade_answer(
            database.sessions,
            None,
            decision_llm,
            None,
            identifier,
            QuestionType.DEFINITION_TO_WORD,
            ResponseFormat.SINGLE_WORD,
            " BANK ",
            policy,
            allowed_pairs=pairs,
        )
        assert exact.sense_id == sense_id and exact.task_fit and not exact.spelling_error
        assert decision_llm.calls == 0
        semantic = await grade_answer(
            database.sessions,
            None,
            decision_llm,
            None,
            identifier,
            QuestionType.WORD_TO_DEFINITION,
            ResponseFormat.SHORT_ANSWER,
            "an institution that holds money",
            policy,
            allowed_pairs=pairs,
        )
        assert semantic.sense_id == sense_id
        assert semantic.accuracy is DefinitionAccuracy.ACCURATE
        assert semantic.coverage is DefinitionCoverage.SUFFICIENT
        assert decision_llm.calls == 2
        with pytest.raises(UnsupportedQuestionFormatError):
            await grade_answer(
                database.sessions,
                None,
                decision_llm,
                None,
                identifier,
                QuestionType.WORD_TO_USAGE,
                ResponseFormat.SHORT_ANSWER,
                "The bank opens.",
                policy,
                allowed_pairs=pairs,
            )
        assert decision_llm.calls == 2
        assert statements and set(statements) == {"select"}
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", observe)
