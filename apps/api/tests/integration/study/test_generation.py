import pytest
from sqlalchemy import func, select
from structlog.testing import capture_logs

from pycil.study.artifacts.generation import generate_artifacts
from pycil.study.enums import QuestionArtifactType
from pycil.study.models import QuestionArtifact
from tests.support.vocabulary import neutral_word


class ExerciseProvider:
    async def complete(self, instruction, data, schema):
        return schema.model_validate(
            {
                "artifacts": [
                    {"context": "The bank is open.", "distractors": ["shop", "school", "park"]},
                    {
                        "context": "A customer wants to deposit money.",
                        "distractors": ["shop", "school", "park"],
                    },
                ]
            }
        )


class UnavailableProvider:
    async def complete(self, *args):
        raise RuntimeError("private upstream payload must not be logged")


async def test_generation_rejects_leaked_answers_and_observes_atomic_failure(database):
    _, sense_id = await neutral_word(database.sessions)
    saved = await generate_artifacts(
        database.sessions,
        ExerciseProvider(),
        None,
        sense_id,
        QuestionArtifactType.CONTEXT_TO_WORD,
        batch_size=2,
    )
    assert len(saved) == 1
    assert saved[0].payload["context"] == "A customer wants to deposit money."
    with capture_logs() as logs, pytest.raises(RuntimeError):
        await generate_artifacts(
            database.sessions,
            UnavailableProvider(),
            None,
            sense_id,
            QuestionArtifactType.CONTEXT_TO_WORD,
        )
    outcomes = [record for record in logs if record["event"] == "operation_completed"]
    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "failed"
    assert outcomes[0]["error_type"] == "RuntimeError"
    assert outcomes[0]["duration_ms"] >= 0
    assert "private upstream payload" not in str(logs)
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(QuestionArtifact)) == 1


async def test_shared_artifact_views_use_maximum_demand_and_reuse_sufficient_bank(database):
    from pycil.study.artifacts.generation import retrieve_artifacts
    from pycil.study.enums import QuestionType

    _, sense_id = await neutral_word(database.sessions)

    class Provider:
        def __init__(self):
            self.calls = 0

        async def complete(self, instruction, data, schema):
            self.calls += 1
            return schema.model_validate(
                {
                    "artifacts": [
                        {
                            "context": "She deposited money at the _.",
                            "correct": {"expression": "bank", "meaning": "a financial institution"},
                            "distractors": [{"expression": "shop", "meaning": "a retail business"}],
                        }
                    ]
                }
            )

    provider = Provider()
    requests = [
        (sense_id, QuestionType.CLOZE_TO_WORD, 1),
        (sense_id, QuestionType.MEANING_IN_CONTEXT, 1),
    ]
    first = await retrieve_artifacts(
        database.sessions, provider, None, requests, distractor_count=1
    )
    second = await retrieve_artifacts(
        database.sessions, provider, None, requests, distractor_count=1
    )
    assert len(first) == len(second) == 1
    assert first[0].id == second[0].id
    assert provider.calls == 1


async def test_unusable_generated_increment_leaves_bank_empty(database):
    from pydantic import ValidationError

    _, sense_id = await neutral_word(database.sessions)

    class Provider:
        async def complete(self, instruction, data, schema):
            return schema.model_validate(
                {
                    "artifacts": [
                        {"context": "The bank is open.", "distractors": ["shop", "school", "park"]}
                    ]
                }
            )

    with pytest.raises(ValidationError, match="no usable artifact increment"):
        await generate_artifacts(
            database.sessions, Provider(), None, sense_id, QuestionArtifactType.CONTEXT_TO_WORD
        )
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(QuestionArtifact)) == 0
