import json

import pytest
from pydantic import ValidationError

from pycil.vocabulary.generation.schemas import (
    Enrichment,
    EnrichmentBatch,
    Inventory,
    validate_inventory,
)


def inventory():
    return dict(
        lemma="bank",
        type="word",
        aliases=[],
        related=[],
        senses=[dict(definition="a financial institution", pos="noun", references=["a1"])],
    )


def enrichment():
    return dict(
        sense_id=1,
        tier="common",
        cefr_level="a2",
        register=None,
        examples=["The [bank] opens."],
        forms=["bank", "banks|pl"],
        patterns=[],
        collocations=["bank account"],
        relations=[],
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"aliases": ["[bank]"]},
        {"related": [{"type": "part_of_phrasal_family", "lemmas": ["bank on"]}]},
        {"senses": inventory()["senses"] * 2},
        {"senses": [inventory()["senses"][0] | {"references": ["a1", "a1"]}]},
        {"senses": [inventory()["senses"][0] | {"definition": " "}]},
    ],
)
def test_inventory_rejects_invented_identity_and_duplicate_evidence(changes):
    with pytest.raises(ValidationError):
        Inventory.model_validate(inventory() | changes)


def test_inventory_can_only_cite_supplied_evidence():
    value = Inventory.model_validate(inventory())
    validate_inventory(value, {"a1", "w1"})
    with pytest.raises(ValueError, match="not supplied"):
        validate_inventory(value, {"w1"})


@pytest.mark.parametrize("model", [Inventory, EnrichmentBatch])
def test_generation_schemas_use_closed_objects_for_structured_outputs(model):
    schema = model.model_json_schema()
    assert "propertyNames" not in json.dumps(schema)
    for definition in [schema, *schema.get("$defs", {}).values()]:
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"forms": ["banks|bad"]},
        {"patterns": ["bank(s)"]},
        {"relations": [{"type": "synonym", "lemmas": ["[lender]"]}]},
        {"examples": ["no markup", "[unclosed"]},
    ],
)
def test_enrichment_rejects_invalid_forms_patterns_and_unusable_examples(changes):
    with pytest.raises(ValidationError):
        Enrichment.model_validate(enrichment() | changes)


def test_enrichment_filters_malformed_examples_deduplicates_and_rejects_repeated_sense_identity():
    data = enrichment() | {
        "examples": ["plain text", "The [bank] opens.", "THE [BANK] OPENS.", "[unclosed"]
    }
    value = Enrichment.model_validate(data)
    assert value.examples == ["The [bank] opens."]
    with pytest.raises(ValidationError, match="duplicate enrichment identity"):
        EnrichmentBatch(senses=[value, value])
