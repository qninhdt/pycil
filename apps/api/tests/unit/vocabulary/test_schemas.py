import json
from dataclasses import FrozenInstanceError, replace

import pytest
from pydantic import ValidationError

from pycil.vocabulary.schemas import CachedWord, Sense, Word, sense_adapter


def test_lexical_values_are_slotted_immutable_and_preserve_public_json():
    word = Word.model_validate(
        dict(
            id=1,
            lemma="bank",
            type="word",
            generation_state="done",
            aliases=["banking house"],
            related=[dict(rel_type="word_family", to_word_id=2, to_word_lemma="banking")],
            senses=[
                dict(
                    id=10,
                    word_id=1,
                    pos="noun",
                    tier="core",
                    register="formal",
                    definition=dict(id=20, content="a financial institution"),
                    examples=[dict(id=30, content="The [bank] opens.")],
                    forms=[dict(surface="banks", inf="plural")],
                    patterns=["bank on {sth}"],
                    collocations=["bank account"],
                    relations=[
                        dict(
                            rel_type="synonym",
                            to_word_id=3,
                            to_word_lemma="lender",
                            resolution_state="pending",
                        )
                    ],
                )
            ],
        )
    )
    sense = word.senses[0]
    cached = CachedWord(
        id=word.id,
        lemma=word.lemma,
        type=word.type,
        generation_state=word.generation_state,
        sense_ids=[sense.id],
        aliases=word.aliases,
        related=word.related,
    )
    assert cached.sense_ids == (sense.id,)
    assert cached.aliases == ("banking house",)
    assert isinstance(cached.related, tuple)
    for collection in (
        sense.examples,
        sense.forms,
        sense.patterns,
        sense.collocations,
        sense.relations,
    ):
        assert isinstance(collection, tuple)
    for value in (
        cached,
        sense,
        sense.definition,
        *sense.examples,
        *sense.forms,
        *sense.relations,
        *cached.related,
    ):
        assert not hasattr(value, "__dict__")
        field = next(iter(value.__dataclass_fields__))
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, getattr(value, field))
    trimmed = replace(sense, examples=())
    assert trimmed.examples == () and len(sense.examples) == 1
    assert trimmed.definition is sense.definition
    assert trimmed.register_ is sense.register_
    payload = word.model_dump(mode="json")
    assert payload["senses"][0]["register"] == "formal"
    assert "register_" not in payload["senses"][0]
    assert payload["senses"][0]["definition"]["theme_id"] is None
    assert Word.model_validate_json(word.model_dump_json()).model_dump(mode="json") == payload
    assert json.loads(sense_adapter.dump_json(sense)) == payload["senses"][0]
    assembled = Word(
        id=cached.id,
        lemma=cached.lemma,
        type=cached.type,
        generation_state=cached.generation_state,
        aliases=cached.aliases,
        related=cached.related,
        senses=[sense],
    )
    assert assembled.senses[0] is sense
    assert assembled.related[0] is cached.related[0]
    assert assembled.model_dump(mode="json") == payload


@pytest.mark.parametrize(
    "change",
    [
        {"unexpected": True},
        {"pos": "invalid"},
        {"id": "invalid"},
        {"examples": [{"id": 1, "content": "x", "unexpected": True}]},
    ],
)
def test_lexical_validation_rejects_invalid_values(change):
    with pytest.raises(ValidationError):
        sense_adapter.validate_python(dict(id=1, word_id=1, pos="noun", tier="core") | change)


def test_lexical_collection_defaults_are_empty_tuples():
    sense = Sense(id=1, word_id=1, pos="noun", tier="core")
    assert (sense.examples, sense.forms, sense.patterns, sense.collocations, sense.relations) == (
        (),
        (),
        (),
        (),
        (),
    )
