import pytest

from pycil.vocabulary.revisions import ContentRevision


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


@pytest.mark.parametrize("entity_type", ["theme", "question_artifact", "unknown"])
def test_revision_rejects_non_vocabulary_entities(entity_type):
    with pytest.raises(ValueError, match="Only vocabulary"):
        ContentRevision(
            entity_type=entity_type, entity_id=1, op=[{"op": "add", "path": "", "value": {}}]
        )
