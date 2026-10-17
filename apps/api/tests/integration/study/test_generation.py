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


async def test_generation_rejects_leaked_answers_and_observes_atomic_failure(
    database, operation_metrics
):
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
    points = operation_metrics()
    assert {point.attributes["operation"] for point in points} == {"artifact_generation"}
    assert {point.attributes["outcome"]: point.count for point in points} == {
        "succeeded": 1,
        "failed": 1,
    }
    async with database.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(QuestionArtifact)) == 1


async def test_shared_artifact_views_use_maximum_demand_and_reuse_sufficient_bank(
    database, operation_metrics
):
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
    points = operation_metrics()
    assert len(points) == 1 and points[0].count == 1
    assert points[0].attributes == {"operation": "artifact_generation", "outcome": "succeeded"}


async def test_unusable_generated_increment_leaves_bank_empty(database, operation_metrics):
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
    points = operation_metrics()
    assert len(points) == 1 and points[0].count == 1
    assert points[0].attributes == {"operation": "artifact_generation", "outcome": "failed"}


@pytest.mark.parametrize("singleton", [False, True])
async def test_concurrent_preparations_generate_without_waiting_and_preserve_increments(
    database, singleton
):
    import asyncio

    from pycil.study.artifacts.generation import retrieve_artifacts
    from pycil.study.enums import QuestionType

    _, sense_id = await neutral_word(database.sessions)
    all_started = asyncio.Event()

    class Provider:
        calls = 0

        async def complete(self, instruction, data, schema):
            self.calls += 1
            number = self.calls
            if number == 4:
                all_started.set()
            await all_started.wait()
            payload = (
                {
                    "corrects": [f"a financial institution serving customer {number}"],
                    "distractors": [{"word": "shop", "definition": "a retail business"}],
                }
                if singleton
                else {
                    "context": f"Customer {number} deposited money at the _.",
                    "correct": {"expression": "bank", "meaning": "a financial institution"},
                    "distractors": [{"expression": "shop", "meaning": "a retail business"}],
                }
            )
            return schema.model_validate({"artifacts": [payload]})

    provider = Provider()
    question_type = QuestionType.WORD_TO_DEFINITION if singleton else QuestionType.CLOZE_TO_WORD
    async with asyncio.timeout(5):
        results = await asyncio.gather(
            *(
                retrieve_artifacts(
                    database.sessions,
                    provider,
                    None,
                    [(sense_id, question_type, 1)],
                    distractor_count=1,
                )
                for _ in range(4)
            )
        )
    assert provider.calls == 4
    assert all(len(result) == 1 for result in results)
    async with database.sessions() as session:
        rows = list(await session.scalars(select(QuestionArtifact)))
    if singleton:
        import orjson

        assert len(rows) == 1
        assert len(orjson.loads(rows[0].payload)["corrects"]) == 4
    else:
        assert len(rows) == 4
        assert len({row.payload_hash for row in rows}) == 4
