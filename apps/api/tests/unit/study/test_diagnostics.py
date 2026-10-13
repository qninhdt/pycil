import pytest
from pydantic import ValidationError

from pycil.study.schemas import DefinitionDiagnostic, RewriteDiagnostic, UsageDiagnostic


@pytest.mark.parametrize(
    "data",
    [
        {"sense_id": 1, "accuracy": None, "coverage": "sufficient"},
        {"sense_id": None, "accuracy": "accurate", "coverage": None},
        {"sense_id": None, "accuracy": None, "coverage": "partial"},
    ],
)
def test_definition_diagnostics_cannot_claim_quality_without_matched_sense(data):
    with pytest.raises(ValidationError):
        DefinitionDiagnostic(**data)


@pytest.mark.parametrize("used", [True, False])
def test_usage_presence_requires_exactly_the_corresponding_rubric(used):
    fields = dict(
        meaning="correct", form="correct", construction=True, collocation=True, appropriacy=True
    )
    valid = fields if used else dict.fromkeys(fields)
    assert UsageDiagnostic(used=used, **valid).used is used
    invalid = valid | {"construction": None if used else True}
    with pytest.raises(ValidationError):
        UsageDiagnostic(used=used, **invalid)
    with pytest.raises(ValidationError):
        RewriteDiagnostic(used=used, **valid, meaning_preservation=None if used else "preserved")
