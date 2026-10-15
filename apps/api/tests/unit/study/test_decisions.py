import json

import httpx
import pytest

from pycil.app.config import load_config
from pycil.infrastructure.llm import DecisionLLM
from pycil.infrastructure.retry import ProviderOutputError
from pycil.study.decisions import (
    DefinitionAssessment,
    RewriteAssessment,
    TargetUseAssessment,
    UsageAssessment,
    sense_selection_model,
    single_word_model,
)
from pycil.study.enums import QuestionType


@pytest.mark.parametrize(
    "schema, answers, predicates",
    [
        (DefinitionAssessment, {"accuracy": "mixed", "coverage": "partial"}, set()),
        (TargetUseAssessment, {"used": 0.8}, {"used"}),
        (
            UsageAssessment,
            {
                "meaning": "approximate",
                "form": "spelling_error",
                "construction": 0.1,
                "collocation": 0.9,
                "appropriacy": 0.7,
            },
            {"construction", "collocation", "appropriacy"},
        ),
        (
            RewriteAssessment,
            {
                "meaning": "correct",
                "form": "form_error",
                "construction": 0.8,
                "collocation": 0.2,
                "appropriacy": 0.3,
                "meaning_preservation": "changed",
            },
            {"construction", "collocation", "appropriacy"},
        ),
        *[
            (
                single_word_model(kind),
                {"task_fit": 0.8, "spelling_error": 0.2},
                {"task_fit", "spelling_error"},
            )
            for kind in (
                QuestionType.DEFINITION_TO_WORD,
                QuestionType.CONTEXT_TO_WORD,
                QuestionType.CLOZE_TO_WORD,
            )
        ],
    ],
)
async def test_grading_models_expose_complete_native_questions_and_typed_answers(
    schema, answers, predicates
):
    context = {
        "word": "bank",
        "meaning": "financial institution",
        "question": "definition",
        "answer": "learner answer",
        "source": "original sentence",
    }

    async def respond(request):
        body = json.loads(request.content)
        assert body["state"] == context
        assert set(body["questions"]) == set(answers)
        envelope = {}
        for name, value in answers.items():
            question = body["questions"][name]
            assert question["instructions"].strip()
            kind = "noul" if name in predicates else "choice"
            assert question["type"] == kind
            if kind == "noul":
                assert set(question["criteria"]) == {"true", "false"}
            else:
                assert value in question["criteria"]
                assert all(question["criteria"].values())
            envelope[name] = {"type": kind, kind: value}
        return httpx.Response(200, json={"answers": envelope})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = DecisionLLM(
            load_config().runtime.providers.vocabulary,
            api_key="test",
            endpoint="https://decision.test",
            http_client=http,
        )
        result = await client.decide(schema, context)
    assert result.model_dump() == answers


@pytest.mark.parametrize("field", ["matched_sense", "defined_meaning"])
async def test_dynamic_meaning_choices_keep_evidence_and_reject_previous_inventory(field):
    requests = []
    policy = load_config().runtime.providers.vocabulary.model_copy(update={"max_retries": 0})

    async def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        criteria = body["questions"][field]["criteria"]
        assert "no_candidate" in criteria
        if len(requests) == 1:
            assert criteria["sense_12"] == "bank - noun - financial institution"
            assert criteria["sense_35"] == "bank - noun - river edge"
        else:
            assert set(criteria) == {"no_candidate", "sense_77"}
        return httpx.Response(
            200, json={"answers": {field: {"type": "choice", "choice": "sense_12"}}}
        )

    first = {
        "lemma": "bank",
        "senses": [
            {"id": 12, "pos": "noun", "definition": "financial institution"},
            {"id": 35, "pos": "noun", "definition": "river edge"},
        ],
    }
    second = {
        "lemma": "lender",
        "senses": [
            {"id": 77, "pos": "noun", "definition": "someone who lends money"},
        ],
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = DecisionLLM(
            policy, api_key="test", endpoint="https://decision.test", http_client=http
        )
        result = await client.decide(sense_selection_model(field, first), {"answer": "learner"})
        assert getattr(result, field) == "sense_12"
        with pytest.raises(ProviderOutputError):
            await client.decide(sense_selection_model(field, second), {"answer": "learner"})
    assert len(requests) == 2
