from uuid import uuid4

import pytest
from pydantic import ValidationError

from pycil.library.schemas import NodeDestination, NodeMove, NodePatch, SenseDelta


@pytest.mark.parametrize(
    "schema, values",
    [
        (NodePatch, {}),
        (NodePatch, {"name": None}),
        (NodePatch, {"name": "   "}),
        (NodePatch, {"name": "a" * 256}),
        (NodePatch, {"description": "a" * 8001}),
        (NodePatch, {"name": "deck", "sense_ids": [1]}),
        (NodePatch, {"description": None, "parent_id": str(uuid4())}),
        (SenseDelta, {"add": [True]}),
        (SenseDelta, {"add": ["1"]}),
        (SenseDelta, {"remove": [0]}),
        (SenseDelta, {"add": [1, 1]}),
        (SenseDelta, {"remove": [1, 1]}),
        (SenseDelta, {"add": [1], "remove": [1]}),
        (SenseDelta, {"add": list(range(1, 1002))}),
        (NodeMove, {"parent_id": None}),
        (NodeMove, {"parent_id": str(uuid4()), "sense_ids": [1]}),
        (NodeDestination, {"parent_id": str(uuid4()), "owner_id": str(uuid4())}),
    ],
)
def test_targeted_writes_reject_invalid_or_unrelated_fields(schema, values):
    with pytest.raises(ValidationError):
        schema.model_validate(values)


def test_metadata_patch_preserves_omitted_fields_and_can_clear_description():
    assert NodePatch(description=None).model_dump(exclude_unset=True) == {"description": None}
    assert NodePatch(name="new name").model_dump(exclude_unset=True) == {"name": "new name"}
    assert SenseDelta(add=[1], remove=[2]).model_dump() == {"add": [1], "remove": [2]}
    assert not NodeMove(parent_id=uuid4()).confirm_publication
