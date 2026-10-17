"""Generate missing exercise banks through the shared provider boundary."""

import asyncio
from collections.abc import Sequence
from typing import Any, cast

from pydantic import Field, create_model, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pycil.infrastructure.kv_store import InMemoryStore
from pycil.infrastructure.llm import StructuredLLMProtocol, render_prompt
from pycil.observability import get_logger, observe_operation
from pycil.study.artifacts.schemas import (
    ARTIFACT_SCHEMAS,
    Artifact,
    ArtifactPayload,
    Strict,
    validate_artifact,
)
from pycil.study.artifacts.storage import (
    append,
    bank_sizes,
    generation_context,
    retrieve_many,
)
from pycil.study.enums import (
    QUESTION_ARTIFACT_MAP,
    SINGLETON_ARTIFACT_TYPES,
    QuestionArtifactType,
    QuestionType,
)
from pycil.vocabulary.errors import InvalidOutputError, InvalidResourceError
from pycil.vocabulary.models import Definition, Sense
from pycil.vocabulary.schemas import forms_adapter

logger = get_logger(__name__)


async def generate_artifacts(
    sessions: async_sessionmaker[AsyncSession],
    structured_llm: StructuredLLMProtocol,
    store: InMemoryStore[int, Artifact] | None,
    sense_id: int,
    kind: QuestionArtifactType | str,
    batch_size: int = 1,
    *,
    correct_count: int = 1,
    distractor_count: int = 3,
    theme_key: str | None = None,
) -> list[Artifact]:
    with observe_operation(
        logger, "artifact_generation", sense_id=sense_id, artifact_type=str(kind)
    ):
        artifact_kind = QuestionArtifactType(kind)
        if (
            type(batch_size) is not int
            or not 1 <= batch_size <= 20
            or any(
                type(value) is not int or not 1 <= value <= 20
                for value in (correct_count, distractor_count)
            )
        ):
            raise InvalidResourceError("invalid artifact generation limits")
        word, sense, theme = await generation_context(sessions, sense_id, theme_key=theme_key)
        assert sense.definition is not None, "sense definition is required"
        context: dict[str, object] = dict(
            word=word.lemma,
            pos=sense.pos,
            definition=sense.definition.content,
            distractor_count=distractor_count,
        )
        singleton = artifact_kind in SINGLETON_ARTIFACT_TYPES
        context["correct_count" if singleton else "batch_size"] = (
            correct_count if singleton else batch_size
        )
        if artifact_kind is QuestionArtifactType.WORD_DEFINITION:
            async with sessions() as session:
                context["other_definitions"] = list(
                    await session.scalars(
                        select(Definition.content)
                        .join(Sense, Sense.id == Definition.sense_id)
                        .where(
                            Sense.word_id == word.id,
                            Sense.id != sense.id,
                            Definition.theme_id == (theme["id"] if theme else None),
                        )
                    )
                )
        if artifact_kind in {
            QuestionArtifactType.WORD_TO_USAGE,
            QuestionArtifactType.CONTEXT_WORD_MEANING,
            QuestionArtifactType.DIALOGUE_COMPLETION,
            QuestionArtifactType.SENTENCE_REWRITE,
        }:
            if sense.forms:
                context["forms"] = forms_adapter.dump_python(sense.forms, mode="json")
            if sense.patterns:
                context["patterns"] = sense.patterns
        if artifact_kind is QuestionArtifactType.WORD_TO_USAGE and sense.collocations:
            context["collocations"] = sense.collocations
        if (
            artifact_kind
            in {
                QuestionArtifactType.WORD_TO_USAGE,
                QuestionArtifactType.DIALOGUE_COMPLETION,
            }
            and sense.register_
        ):
            context["register"] = sense.register_
        if theme:
            context["theme"] = {name: theme[name] for name in ("voice", "diction")}
        payload_schema = ARTIFACT_SCHEMAS[artifact_kind]

        def usable(data: object) -> object:
            if not isinstance(data, dict):
                return data
            raw_dict = cast(dict[str, object], data)
            artifacts_list = raw_dict.get("artifacts")
            if not isinstance(artifacts_list, list):
                return raw_dict
            accepted: list[dict[str, object]] = []
            for raw in cast(list[object], artifacts_list):
                try:
                    payload = payload_schema.model_validate(raw)
                    validate_artifact(
                        payload,
                        artifact_kind,
                        word,
                        sense,
                        distractor_count,
                        correct_count,
                    )
                except (ValueError, InvalidOutputError):
                    continue
                accepted.append(payload.model_dump())
            if not accepted or (singleton and len(accepted) != 1):
                raise ValueError("no usable artifact increment")
            return {"artifacts": accepted}

        validator_wrapper = cast(Any, model_validator(mode="before")(cast(Any, usable)))
        schema = create_model(
            "ArtifactBatch",
            __base__=Strict,
            artifacts=(
                cast(Any, list[payload_schema]),
                Field(min_length=1, max_length=1 if singleton else 20),
            ),
            __validators__=cast(Any, {"usable": validator_wrapper}),
        )
        instruction, data = render_prompt(
            "study/artifacts/prompts/generate_artifacts.jinja",
            artifact_type=artifact_kind,
            context=context,
        )
        output = await structured_llm.complete(instruction, data, schema)
        raw_output_artifacts = cast(list[ArtifactPayload], getattr(output, "artifacts", []))
        saved = await append(
            sessions,
            [
                Artifact(
                    id=0,
                    sense_id=sense_id,
                    theme_id=theme["id"] if theme else None,
                    artifact_type=artifact_kind,
                    payload=payload.model_dump(),
                )
                for payload in raw_output_artifacts
            ],
            store=store,
        )
        logger.info("artifact_generation_completed", artifacts=len(saved))
        return saved


async def retrieve_artifacts(
    sessions: async_sessionmaker[AsyncSession],
    structured_llm: StructuredLLMProtocol,
    store: InMemoryStore[int, Artifact] | None,
    requests: Sequence[tuple[int, QuestionType, int]],
    *,
    generation_batch_size: int = 1,
    correct_count: int = 1,
    distractor_count: int = 3,
    theme_key: str | None = None,
) -> list[Artifact]:
    demands: dict[tuple[int, QuestionArtifactType], int] = {}
    for sense_id, question_type, quantity in requests:
        if type(quantity) is not int or quantity < 1:
            raise ValueError("invalid artifact quantity")
        kind = QUESTION_ARTIFACT_MAP[question_type]
        q = 1 if kind in SINGLETON_ARTIFACT_TYPES else quantity
        demands[sense_id, kind] = max(demands.get((sense_id, kind), 0), q)
    sizes = await bank_sizes(sessions, list(demands), theme_key=theme_key)

    tasks = [
        asyncio.create_task(
            generate_artifacts(
                sessions,
                structured_llm,
                store,
                sense_id,
                kind,
                max(quantity - sizes[sense_id, kind], generation_batch_size),
                correct_count=correct_count,
                distractor_count=distractor_count,
                theme_key=theme_key,
            )
        )
        for (sense_id, kind), quantity in demands.items()
        if sizes[sense_id, kind] < quantity
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return await retrieve_many(
        sessions,
        [(sense_id, kind, quantity) for (sense_id, kind), quantity in demands.items()],
        theme_key=theme_key,
        store=store,
    )
