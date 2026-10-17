import json

import pytest

from pycil.vocabulary.references.schemas import SourceWord
from tests.support.reference import reference_word


@pytest.mark.parametrize("field,value", [("id", True), ("id", -1), ("lemma", " "), ("senses", [])])
def test_rejects_invalid_word_identity(field, value):
    record = reference_word() | {field: value}
    with pytest.raises(ValueError):
        SourceWord.model_validate_json(json.dumps(record))


def test_rejects_duplicate_senses_in_word():
    record = reference_word()
    record["senses"] *= 2
    with pytest.raises(ValueError, match="duplicate source sense"):
        SourceWord.model_validate_json(json.dumps(record))


def test_retains_source_labels_and_definition_without_guessing():
    record = reference_word(definition=" A definition with deliberate punctuation. ")
    record["senses"][0]["pos"] = "noun or exclamation"
    word = SourceWord.model_validate_json(json.dumps(record))
    assert word.senses[0].pos == "noun or exclamation"
    assert word.senses[0].definition == record["senses"][0]["definition"]
