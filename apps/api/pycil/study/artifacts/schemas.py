"""Saved exercise payloads and lexical answer integrity."""

import re
from collections.abc import Iterable
from typing import Annotated, Any, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pycil.study.enums import QuestionArtifactType
from pycil.vocabulary.errors import InvalidOutputError
from pycil.vocabulary.patterns import matches_pattern
from pycil.vocabulary.schemas import Sense as SenseSchema
from pycil.vocabulary.text import (
    WordLike,
    answer_key,
    components,
    marked_occurrences,
    parse_marked_example,
    strip_markup,
    target_sequences,
)

Text = Annotated[str, Field(min_length=1, max_length=8000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WordDefinitionPair(Strict):
    word: Text
    definition: Text


class WordDefinitionArtifact(Strict):
    corrects: list[Text]
    distractors: list[WordDefinitionPair]


class UsageArtifact(Strict):
    corrects: list[Text]
    distractors: list[Text]


class ContextPair(Strict):
    expression: Text
    meaning: Text


class ContextWordMeaningArtifact(Strict):
    context: Text
    correct: ContextPair
    distractors: list[ContextPair] = Field(min_length=1)


class ContextToWordArtifact(Strict):
    context: Text
    distractors: list[Text] = Field(min_length=1)


class CompletionPoint(Strict):
    turn_index: int = Field(strict=True, ge=0)
    distractors: list[Text] = Field(min_length=1)


class DialogueArtifact(Strict):
    conversation: list[dict[str, Text]] = Field(min_length=4)
    completion_points: list[CompletionPoint] = Field(min_length=1)

    @model_validator(mode="after")
    def complete_dialogue(self) -> Self:
        if any(len(turn) != 1 or not next(iter(turn)).strip() for turn in self.conversation):
            raise ValueError("each dialogue turn needs one named speaker")
        indices = [point.turn_index for point in self.completion_points]
        if len(set(indices)) != len(indices) or any(
            index >= len(self.conversation) for index in indices
        ):
            raise ValueError("invalid or duplicated dialogue completion point")
        return self


class RewriteArtifact(Strict):
    source: Text
    correct: Text
    distractors: list[Text] = Field(min_length=1)


class Artifact(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: int
    sense_id: int
    theme_id: int | None
    artifact_type: QuestionArtifactType
    payload: dict[str, Any]


type ArtifactPayload = (
    WordDefinitionArtifact
    | UsageArtifact
    | ContextWordMeaningArtifact
    | ContextToWordArtifact
    | DialogueArtifact
    | RewriteArtifact
)


ARTIFACT_SCHEMAS: dict[QuestionArtifactType, type[ArtifactPayload]] = {
    QuestionArtifactType.WORD_DEFINITION: WordDefinitionArtifact,
    QuestionArtifactType.WORD_TO_USAGE: UsageArtifact,
    QuestionArtifactType.CONTEXT_WORD_MEANING: ContextWordMeaningArtifact,
    QuestionArtifactType.CONTEXT_TO_WORD: ContextToWordArtifact,
    QuestionArtifactType.DIALOGUE_COMPLETION: DialogueArtifact,
    QuestionArtifactType.SENTENCE_REWRITE: RewriteArtifact,
}


def distinct_options(texts: Iterable[str]) -> None:
    keys = [answer_key(strip_markup(text)) for text in texts]
    if len(keys) != len(set(keys)):
        raise InvalidOutputError("repeated exercise option")


def validate_artifact(
    payload: ArtifactPayload,
    kind: QuestionArtifactType,
    word: WordLike,
    sense: SenseSchema,
    distractor_count: int,
    correct_count: int,
) -> None:
    sequences = target_sequences(word, sense)

    def hidden(text: str) -> None:
        if parse_marked_example(text)[1] or any(
            re.search(
                r"(?<!\w)" + r"\s+".join(map(re.escape, sequence)) + r"(?!\w)", answer_key(text)
            )
            for sequence in sequences
            if sequence
        ):
            raise InvalidOutputError("hidden context reveals the target")

    if kind is QuestionArtifactType.WORD_DEFINITION:
        assert isinstance(payload, WordDefinitionArtifact)
        distinct_options([*payload.corrects, *(pair.definition for pair in payload.distractors)])
        distinct_options([pair.word for pair in payload.distractors])
        if any(components(pair.word) in sequences for pair in payload.distractors):
            raise InvalidOutputError("distractor repeats a target form")
    elif kind is QuestionArtifactType.WORD_TO_USAGE:
        assert isinstance(payload, UsageArtifact)
        distinct_options([*payload.corrects, *payload.distractors])
        for text in [*payload.corrects, *payload.distractors]:
            marked_occurrences(text, sequences)
    elif kind is QuestionArtifactType.CONTEXT_WORD_MEANING:
        assert isinstance(payload, ContextWordMeaningArtifact)
        hidden(payload.context)
        if payload.context.count("_") != 1:
            raise InvalidOutputError("context needs one blank")
        head, _, tail = answer_key(word.lemma).partition(" ")
        forms: dict[str, list[str]] = {
            head: [
                value.partition(" ")[0]
                for form in sense.forms
                if not (value := answer_key(form.surface)).partition(" ")[2]
                or value.partition(" ")[2] == tail
            ]
        }
        licensed: list[str] = [
            word.lemma,
            *word.aliases,
            *sense.patterns,
            *(
                form.surface
                for form in sense.forms
                if len(components(form.surface)) >= len(components(word.lemma))
            ),
        ]
        if not any(
            matches_pattern(pattern, payload.correct.expression, forms=forms)
            for pattern in licensed
        ):
            raise InvalidOutputError("correct expression is not licensed by the sense")
        distinct_options(
            [payload.correct.expression, *(pair.expression for pair in payload.distractors)]
        )
        distinct_options([payload.correct.meaning, *(pair.meaning for pair in payload.distractors)])
    elif kind is QuestionArtifactType.CONTEXT_TO_WORD:
        assert isinstance(payload, ContextToWordArtifact)
        hidden(payload.context)
        if "_" in payload.context:
            raise InvalidOutputError("situation must not be a cloze")
        distinct_options([word.lemma, *payload.distractors])
        if any(components(text) in sequences for text in payload.distractors):
            raise InvalidOutputError("distractor repeats a target alias")
    elif kind is QuestionArtifactType.SENTENCE_REWRITE:
        assert isinstance(payload, RewriteArtifact)
        hidden(payload.source)
        distinct_options([payload.correct, *payload.distractors])
        for text in [payload.correct, *payload.distractors]:
            marked_occurrences(text, sequences)
    elif kind is QuestionArtifactType.DIALOGUE_COMPLETION:
        assert isinstance(payload, DialogueArtifact)
        texts: list[str] = [next(iter(turn.values())) for turn in payload.conversation]
        if sum(marked_occurrences(text, sequences, required=False) for text in texts) != 1:
            raise InvalidOutputError("dialogue needs exactly one marked target")
        for point in payload.completion_points:
            original = texts[point.turn_index]
            distinct_options([original, *point.distractors])
            for text in point.distractors:
                if parse_marked_example(original)[1]:
                    marked_occurrences(text, sequences)
                elif parse_marked_example(text)[1]:
                    raise InvalidOutputError("replacement adds an unrelated target tag")
            if len(point.distractors) != distractor_count:
                raise InvalidOutputError("incomplete dialogue option set")
        return
    if len(payload.distractors) != distractor_count:
        raise InvalidOutputError("incomplete distractor set")
    if (
        kind in {QuestionArtifactType.WORD_DEFINITION, QuestionArtifactType.WORD_TO_USAGE}
        and len(cast(WordDefinitionArtifact | UsageArtifact, payload).corrects) != correct_count
    ):
        raise InvalidOutputError("incomplete correct option set")
