"""Known statistics surface and large-set query contract gaps."""

import pytest

from pycil.hierarchy import subtree
from pycil.main import create_app


@pytest.mark.parametrize(
    "path",
    [
        "/folders/{node_id}/items",
        "/folders/{node_id}/history",
        "/me/stats",
    ],
)
def test_openapi_exposes_approved_statistics_surfaces(path):
    assert path in create_app().openapi()["paths"]


def test_stats_endpoint_has_no_caller_controlled_mastery_threshold():
    operation = create_app().openapi()["paths"]["/folders/{node_id}/stats"]["get"]
    query_parameters = {
        item["name"] for item in operation.get("parameters", []) if item["in"] == "query"
    }

    assert "mastered_threshold" not in query_parameters


async def test_large_subtree_path_has_no_expanding_identifier_bind(monkeypatch):
    async def many_decks(session, root_id, viewer_id=None):
        return list(range(100_000))

    class CapturingSession:
        async def execute(self, statement, parameters):
            expanding = [
                bind.expanding for bind in getattr(statement, "_bindparams", {}).values()
            ]
            assert not any(expanding)

            class EmptyResult:
                def __iter__(self):
                    return iter(())

            return EmptyResult()

    monkeypatch.setattr(subtree, "resolve_deck_ids", many_decks)

    assert await subtree.resolve_sense_ids(CapturingSession(), "root") == []
