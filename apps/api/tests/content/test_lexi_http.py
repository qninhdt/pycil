"""Contract tests for the Pycil-side Lexi HTTP adapter."""

import json

import httpx
import pytest

from pycil.content.lexi_http import LexiHttpClient
from pycil.content.lexi_types import SearchResult

pytestmark = pytest.mark.asyncio


async def test_search_maps_proto_json_and_sends_internal_token():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-lexi-service-token"] == "internal-token"
        assert request.url.path == "/v1/search"
        assert request.url.params["query"] == "run"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "display": "run",
                        "entry_type": "verb",
                        "score": 0.8,
                        "lexi_word_id": "41",
                        "cambridge_id": "0",
                        "gloss": "move quickly",
                    }
                ]
            },
        )

    client = LexiHttpClient(
        "http://lexi-service:8443",
        "internal-token",
        "dataset",
        transport=httpx.MockTransport(handler),
    )
    try:
        results = await client.search("run")
    finally:
        await client.close()

    assert results == [
        SearchResult(
            display="run",
            entry_type="verb",
            score=0.8,
            lexi_word_id=41,
            cambridge_id=None,
            gloss="move quickly",
        )
    ]


async def test_question_projection_and_grading_use_only_service_contract():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "question": {
                        "question_id": 7,
                        "sense_id": 11,
                        "format": "definition_mcq",
                        "answer_kind": "choice_index",
                        "presentation": {
                            "type": "definition_mcq",
                            "stem": "Choose the definition.",
                            "options": ["move", "sleep"],
                        },
                    }
                },
            )
        assert request.url.path == "/v1/questions/7/grade"
        assert json.loads(request.content) == {"answer": "0"}
        return httpx.Response(
            200,
            json={"correct": True, "score": 1.0, "kind": "rule", "feedback": None},
        )

    client = LexiHttpClient(
        "http://lexi-service:8443",
        "internal-token",
        "dataset",
        transport=httpx.MockTransport(handler),
    )
    try:
        question = await client.get_question(7)
        assert question is not None
        assert question.payload == {
            "stem": "Choose the definition.",
            "options": ["move", "sleep"],
        }
        score = await client.grade(question, "0")
    finally:
        await client.close()

    assert score.correct is True
    assert score.score == 1.0
