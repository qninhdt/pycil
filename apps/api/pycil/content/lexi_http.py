"""HTTP adapter for the authenticated internal Lexi service."""

import asyncio
from typing import Any
from uuid import uuid4

import httpx

from pycil.common.errors import ServiceUnavailableError
from pycil.content.lexi_types import Entry, Question, Score, SearchResult, SenseView


class LexiHttpClient:
    """Translate Pycil's narrow port to Lexi's versioned HTTP contract."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        reference_dataset_fingerprint: str,
        *,
        timeout_seconds: float = 15,
        generation_timeout_seconds: float = 120,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Lexi-Service-Token": service_token},
            timeout=timeout_seconds,
            transport=transport,
        )
        self._reference_dataset_fingerprint = reference_dataset_fingerprint
        self._generation_timeout_seconds = generation_timeout_seconds

    async def close(self) -> None:
        await self._client.aclose()

    async def readiness(self) -> bool:
        try:
            response = await self._client.get("/readyz")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def search(self, query: str) -> list[SearchResult]:
        body = await self._request("GET", "/v1/search", params={"query": query})
        return [_search_result(value) for value in body["results"]]

    async def generate(self, source: SearchResult | str) -> Entry:
        target = _search_result_body(source)
        submission = await self._request(
            "POST",
            "/v1/generations",
            headers={"Idempotency-Key": f"pycil-{uuid4().hex}"},
            json={
                "target": target,
                "reference_dataset_fingerprint": self._reference_dataset_fingerprint,
            },
        )
        job_id = submission["job_id"]
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._generation_timeout_seconds
        while loop.time() < deadline:
            job = await self._request("GET", f"/v1/jobs/{job_id}")
            if job["status"] == "succeeded":
                result = job.get("result") or {}
                word_id = result.get("word_id")
                if not isinstance(word_id, int):
                    raise ServiceUnavailableError("lexi_generation_result_invalid")
                entry = await self.get_entry(word_id)
                if entry is None:
                    raise ServiceUnavailableError("lexi_generation_entry_missing")
                return entry
            if job["status"] in {"failed", "expired", "superseded", "dead_letter"}:
                raise ServiceUnavailableError("lexi_generation_failed")
            await asyncio.sleep(0.5)
        raise ServiceUnavailableError("lexi_generation_timed_out")

    async def get_entry(self, word_id: int) -> Entry | None:
        body = await self._request("GET", f"/v1/entries/{word_id}", allow_not_found=True)
        return None if body is None else _entry(body["entry"])

    async def get_senses(self, sense_ids: list[int]) -> list[SenseView]:
        if not sense_ids:
            return []
        body = await self._request(
            "GET", "/v1/senses", params=[("id", value) for value in sense_ids]
        )
        return [_sense(value) for value in body["senses"]]

    async def generate_questions(
        self, word_id: int, sense_id: int, formats: list[str], n: int
    ) -> list[Question]:
        body = await self._request(
            "POST",
            "/v1/questions/generations",
            json={"word_id": word_id, "sense_id": sense_id, "formats": formats, "count": n},
        )
        return [_question(value) for value in body["questions"]]

    async def grade(self, question: Question, answer: str) -> Score:
        if question.id is None:
            raise ValueError("question_requires_persisted_id")
        body = await self._request(
            "POST", f"/v1/questions/{question.id}/grade", json={"answer": answer}
        )
        return Score(
            correct=bool(body["correct"]),
            score=float(body["score"]),
            kind=str(body["kind"]),
            feedback=body.get("feedback"),
        )

    async def get_question(self, question_id: int) -> Question | None:
        body = await self._request("GET", f"/v1/questions/{question_id}", allow_not_found=True)
        return None if body is None else _question(body["question"])

    async def get_question_for_sense(
        self, sense_id: int, question_format: str
    ) -> Question | None:
        body = await self._request(
            "GET",
            "/v1/questions",
            params={"sense_id": sense_id, "format": question_format},
        )
        values = body["questions"]
        return _question(values[0]) if values else None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        allow_not_found: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError("lexi_service_unavailable") from exc
        if allow_not_found and response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ServiceUnavailableError("lexi_service_request_failed")
        return response.json()


def _search_result(value: dict[str, Any]) -> SearchResult:
    return SearchResult(
        display=str(value["display"]),
        entry_type=value.get("entry_type") or None,
        score=float(value.get("score", 0)),
        lexi_word_id=_optional_int(value.get("lexi_word_id")),
        cambridge_id=_optional_int(value.get("cambridge_id")),
        gloss=value.get("gloss") or None,
    )


def _search_result_body(value: SearchResult | str) -> dict[str, Any]:
    if isinstance(value, str):
        return {"display": value}
    return {
        "display": value.display,
        "entry_type": value.entry_type,
        "score": value.score,
        "lexi_word_id": value.lexi_word_id,
        "cambridge_id": value.cambridge_id,
        "gloss": value.gloss,
    }


def _entry(value: dict[str, Any]) -> Entry:
    return Entry(
        word_id=int(value["word_id"]),
        display=str(value["display"]),
        norm=str(value["norm"]),
        status=str(value["status"]),
        entry_type=value.get("entry_type") or None,
        senses=[_sense(sense) for sense in value.get("senses", [])],
    )


def _sense(value: dict[str, Any]) -> SenseView:
    return SenseView(
        definition=str(value["definition"]),
        tier=str(value["tier"]),
        pos=value.get("pos") or None,
        cefr_level=value.get("cefr_level") or None,
        sense_id=_optional_int(value.get("sense_id")),
        examples=[str(example) for example in value.get("examples", [])],
    )


def _question(value: dict[str, Any]) -> Question:
    presentation = dict(value["presentation"])
    question_format = str(presentation.pop("type"))
    return Question(
        id=int(value["question_id"]),
        word_id=0,
        sense_id=int(value["sense_id"]),
        format=question_format,
        answer_kind=str(value["answer_kind"]),
        payload=presentation,
    )


def _optional_int(value: object) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    return int(value)
