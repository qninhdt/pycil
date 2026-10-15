import pytest

from pycil.infrastructure.content_revisions import ContentRevision


@pytest.mark.parametrize(
    "patch",
    [
        None,
        {},
        [],
        [1],
        [{"op": "unknown", "path": ""}],
        [{"op": "replace", "path": ""}],
        [{"op": "remove", "path": "bad"}],
        [{"op": "move", "path": "/a"}],
        [{"op": "copy", "path": "/a", "from": 1}],
    ],
)
def test_revision_rejects_malformed_patch(patch):
    with pytest.raises(ValueError):
        ContentRevision(entity_type="word", entity_id=1, op=patch)
