"""Comprehensive ASGI HTTP integration test suite testing key domain routes.

Covers endpoints that previously lacked ASGI HTTP boundary tests:
1. Account HTTP endpoints:
   - PATCH /v1/me/settings (valid payload -> 200, invalid timezone -> 422)
   - PATCH /v1/me/profile (valid display_name/handle -> 200, missing token -> 401)
   - GET /v1/me/usage (returns usage structure -> 200)
   - GET /v1/users:lookup?handle=... (existing handle -> 200, missing handle -> 404)
2. Library HTTP endpoints:
   - GET /v1/nodes (cursor seek pagination & parent_id query -> 200)
   - POST /v1/nodes/{id}:copy (copy deck to folder -> 200 or 201)
   - POST /v1/nodes/{id}:move (move deck to folder -> 200)
   - DELETE /v1/nodes/{id} (delete non-system node -> 204 or 200)
   - GET /v1/discovery/nodes (public discovery query -> 200)
3. Vocabulary HTTP endpoints:
   - GET /v1/words:search?q=... (returns lexical matches -> 200)
   - POST /v1/words:batchPreview (batch preview words -> 200)
4. Study HTTP endpoints:
   - GET /v1/study/progress (progress summary -> 200)
   - GET /v1/study/activity (daily activity events -> 200)
   - GET /v1/study/review-schedule (review schedule intervals -> 200)
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from pycil.account.models import User
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.infrastructure.clerk import InvalidIdentityError
from pycil.infrastructure.kv_store import InMemoryStore
from pycil.library.models import NodeRole
from pycil.study.artifacts.schemas import Artifact
from pycil.vocabulary.schemas import CachedWord, Sense
from pycil.vocabulary.search import SearchIndex
from tests.support.account import account
from tests.support.vocabulary import neutral_word


class MockIdentity:
    def __init__(self, clerk_id: str):
        self.clerk_id = clerk_id

    async def subject(self, token: str) -> str:
        if token == "test-token":
            return self.clerk_id
        raise InvalidIdentityError("invalid_credentials")


@pytest.fixture
async def app_client(database):
    user, roots = await account(database.sessions)
    async with database.sessions() as session, session.begin():
        saved = await session.get(User, user.id)
        saved.display_name, saved.handle = "Alice", "alice"
    user.display_name, user.handle = "Alice", "alice"

    # Seed a neutral word for vocabulary search & preview tests
    word_id, sense_id = await neutral_word(database.sessions)

    app = create_app()
    app.state.sessions = database.sessions
    app.state.config = load_config()
    app.state.identity = MockIdentity(user.clerk_id)
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    app.state.user_id_store = InMemoryStore[str, UUID](1000, 60.0)
    app.state.word_store = InMemoryStore[int, CachedWord](1000, 60.0)
    app.state.sense_store = InMemoryStore[int, Sense](1000, 60.0)
    app.state.artifact_store = InMemoryStore[int, Artifact](1000, 60.0)

    search_index = SearchIndex(
        database.sessions,
        policy=app.state.config.vocabulary.search_runtime,
        query_policy=app.state.config.vocabulary.search,
    )
    await search_index.start()
    app.state.search = search_index

    headers = {"Authorization": "Bearer test-token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as client:
        yield SimpleNamespace(
            app=app,
            client=client,
            user=user,
            roots=roots,
            headers=headers,
            search=search_index,
            word_id=word_id,
            sense_id=sense_id,
            database=database,
        )

    await search_index.close()


# ---------------------------------------------------------------------------
# 1. Account HTTP Endpoints
# ---------------------------------------------------------------------------


async def test_account_settings_valid_and_invalid_payloads(app_client):
    """PATCH /v1/me/settings: valid settings payload -> 200, invalid timezone -> 422."""
    client = app_client.client
    headers = app_client.headers

    # Valid settings payload
    valid_patch = {"locale": "vi", "assistant": {"auto_approve": True}}
    response = await client.patch("/v1/me/settings", headers=headers, json=valid_patch)
    assert response.status_code == 200
    data = response.json()
    assert data["settings"]["locale"] == "vi"
    assert data["settings"]["assistant"]["auto_approve"] is True

    # Invalid timezone payload -> 422
    invalid_patch = {"timezone": "Invalid/Timezone"}
    response = await client.patch("/v1/me/settings", headers=headers, json=invalid_patch)
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_preferences"

    # Missing authorization token -> 401
    unauth = await client.patch("/v1/me/settings", json=valid_patch)
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.patch(
        "/v1/me/settings", headers={"Authorization": "Bearer bad-token"}, json=valid_patch
    )
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"


async def test_account_profile_valid_and_unauthenticated(app_client):
    """PATCH /v1/me/profile: valid display_name/handle -> 200, missing token -> 401."""
    client = app_client.client
    headers = app_client.headers

    # Valid display_name/handle update
    response = await client.patch(
        "/v1/me/profile",
        headers=headers,
        json={"display_name": "Alice Wonderland", "handle": "alicew"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Alice Wonderland"
    assert data["handle"] == "alicew"

    # Missing authorization token -> 401
    unauth = await client.patch("/v1/me/profile", json={"display_name": "No Auth"})
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.patch(
        "/v1/me/profile",
        headers={"Authorization": "Bearer bad-token"},
        json={"display_name": "Bad Auth"},
    )
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"


async def test_account_usage_returns_allowance_structure(app_client):
    """GET /v1/me/usage: returns usage structure -> 200."""
    client = app_client.client
    headers = app_client.headers

    # Missing authorization token -> 401
    unauth = await client.get("/v1/me/usage")
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.get("/v1/me/usage", headers={"Authorization": "Bearer bad-token"})
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"

    response = await client.get("/v1/me/usage", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "period_start" in data
    assert "period_end" in data
    assert isinstance(data["allowance_units"], int)
    assert isinstance(data["used_units"], int)
    assert isinstance(data["remaining_units"], int)


async def test_account_user_lookup_by_handle(app_client):
    """GET /v1/users:lookup?handle=...: existing handle -> 200, missing handle -> 404."""
    client = app_client.client

    # Existing user lookup
    response = await client.get(f"/v1/users:lookup?handle={app_client.user.handle}")
    assert response.status_code == 200
    data = response.json()
    assert data["handle"] == app_client.user.handle
    assert data["id"] == str(app_client.user.id)
    assert "settings" not in data  # Public projection omits private settings

    # Missing handle lookup -> 404
    missing = await client.get("/v1/users:lookup?handle=nonexistent_handle_xyz")
    assert missing.status_code == 404
    assert missing.json()["error"] == "account_not_found"

    # Missing required query param -> 422
    no_param = await client.get("/v1/users:lookup")
    assert no_param.status_code == 422


# ---------------------------------------------------------------------------
# 2. Library HTTP Endpoints
# ---------------------------------------------------------------------------


async def test_library_nodes_cursor_seek_pagination_and_parent_id_query(app_client):
    """GET /v1/nodes: cursor seek pagination & parent_id query -> 200."""
    client = app_client.client
    headers = app_client.headers
    personal_id = app_client.roots[NodeRole.PERSONAL_ROOT].id

    # Create 3 decks under personal root to paginate over
    for name in ["Deck Alpha", "Deck Beta", "Deck Gamma"]:
        create_res = await client.post(
            "/v1/nodes",
            headers=headers,
            json={"type": "deck", "name": name, "parent_id": str(personal_id)},
        )
        assert create_res.status_code == 201

    # First page query with limit=2
    res_page1 = await client.get(
        "/v1/nodes",
        headers=headers,
        params={"parent_id": str(personal_id), "limit": 2},
    )
    assert res_page1.status_code == 200
    page1 = res_page1.json()
    assert len(page1["nodes"]) == 2
    assert page1["next_cursor"] is not None

    # Next page query with cursor
    res_page2 = await client.get(
        "/v1/nodes",
        headers=headers,
        params={"parent_id": str(personal_id), "cursor": page1["next_cursor"], "limit": 2},
    )
    assert res_page2.status_code == 200
    page2 = res_page2.json()
    assert len(page2["nodes"]) == 1

    # Strict query params violation -> 422 invalid_query_parameters
    res_strict = await client.get(
        "/v1/nodes",
        headers=headers,
        params={"parent_id": str(personal_id), "unknown_param": "forbidden"},
    )
    assert res_strict.status_code == 422
    assert res_strict.json()["error"] == "invalid_query_parameters"

    # Invalid cursor -> 422 invalid_cursor
    res_bad_cursor = await client.get(
        "/v1/nodes",
        headers=headers,
        params={"parent_id": str(personal_id), "cursor": "bad.cursor.token"},
    )
    assert res_bad_cursor.status_code == 422
    assert res_bad_cursor.json()["error"] == "invalid_cursor"


async def test_library_copy_deck_to_folder(app_client):
    """POST /v1/nodes/{id}:copy: copy deck to folder -> 200 (or 201)."""
    client = app_client.client
    headers = app_client.headers

    # Create target folder
    folder = (
        await client.post(
            "/v1/nodes",
            headers=headers,
            json={"type": "folder", "name": "Destination Folder"},
        )
    ).json()

    # Create source deck
    source_deck = (
        await client.post(
            "/v1/nodes",
            headers=headers,
            json={"type": "deck", "name": "Copyable Deck"},
        )
    ).json()

    # Missing authorization token -> 401
    unauth = await client.post(
        f"/v1/nodes/{source_deck['id']}:copy",
        json={"parent_id": folder["id"]},
    )
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.post(
        f"/v1/nodes/{source_deck['id']}:copy",
        headers={"Authorization": "Bearer bad-token"},
        json={"parent_id": folder["id"]},
    )
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"

    # Copy deck into folder
    copy_res = await client.post(
        f"/v1/nodes/{source_deck['id']}:copy",
        headers=headers,
        json={"parent_id": folder["id"]},
    )
    assert copy_res.status_code in (200, 201)
    copied = copy_res.json()
    assert copied["name"] == "Copyable Deck"
    assert copied["parent_id"] == folder["id"]
    assert copied["id"] != source_deck["id"]


async def test_library_move_deck_to_folder(app_client):
    """POST /v1/nodes/{id}:move: move deck to folder -> 200."""
    client = app_client.client
    headers = app_client.headers

    # Create target folder
    folder = (
        await client.post(
            "/v1/nodes",
            headers=headers,
            json={"type": "folder", "name": "Move Destination Folder"},
        )
    ).json()

    # Create deck to move
    deck = (
        await client.post(
            "/v1/nodes",
            headers=headers,
            json={"type": "deck", "name": "Movable Deck"},
        )
    ).json()

    # Missing authorization token -> 401
    unauth = await client.post(
        f"/v1/nodes/{deck['id']}:move",
        json={"parent_id": folder["id"]},
    )
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.post(
        f"/v1/nodes/{deck['id']}:move",
        headers={"Authorization": "Bearer bad-token"},
        json={"parent_id": folder["id"]},
    )
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"

    # Move deck into folder
    move_res = await client.post(
        f"/v1/nodes/{deck['id']}:move",
        headers=headers,
        json={"parent_id": folder["id"]},
    )
    assert move_res.status_code == 200
    moved = move_res.json()
    assert moved["id"] == deck["id"]
    assert moved["parent_id"] == folder["id"]


async def test_library_delete_non_system_node(app_client):
    """DELETE /v1/nodes/{id}: delete non-system node -> 204 or 200."""
    client = app_client.client
    headers = app_client.headers

    # Create temporary deck
    deck = (
        await client.post(
            "/v1/nodes",
            headers=headers,
            json={"type": "deck", "name": "Temporary Deck"},
        )
    ).json()

    # Missing authorization token -> 401
    unauth = await client.delete(f"/v1/nodes/{deck['id']}")
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.delete(
        f"/v1/nodes/{deck['id']}", headers={"Authorization": "Bearer bad-token"}
    )
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"

    # Delete deck
    del_res = await client.delete(f"/v1/nodes/{deck['id']}", headers=headers)
    assert del_res.status_code in (200, 204)

    # Confirm it is no longer found
    detail_res = await client.get(f"/v1/nodes/{deck['id']}", headers=headers)
    assert detail_res.status_code == 404


async def test_library_discovery_nodes_query(app_client):
    """GET /v1/discovery/nodes: public discovery query -> 200."""
    client = app_client.client
    headers = app_client.headers
    pub_root = app_client.roots[NodeRole.PUBLISHED_ROOT].id

    # Create a published deck
    await client.post(
        "/v1/nodes",
        headers=headers,
        json={
            "type": "deck",
            "name": "Public Lexicon Deck",
            "parent_id": str(pub_root),
            "confirm_publication": True,
        },
    )

    # Query public discovery
    disc_res = await client.get("/v1/discovery/nodes", params={"q": "Lexicon"})
    assert disc_res.status_code == 200
    data = disc_res.json()
    assert "nodes" in data
    assert any(item["name"] == "Public Lexicon Deck" for item in data["nodes"])

    # Strict query params check: unexpected query param -> 422
    res_strict = await client.get(
        "/v1/discovery/nodes",
        params={"q": "Lexicon", "unauthorized_query": "bad"},
    )
    assert res_strict.status_code == 422
    assert res_strict.json()["error"] == "invalid_query_parameters"


# ---------------------------------------------------------------------------
# 3. Vocabulary HTTP Endpoints
# ---------------------------------------------------------------------------


async def test_vocabulary_search_returns_lexical_matches(app_client):
    """GET /v1/words:search?q=...: returns lexical matches -> 200."""
    client = app_client.client

    # Search with q parameter
    res_q = await client.get("/v1/words:search", params={"q": "bank"})
    assert res_q.status_code == 200
    data_q = res_q.json()
    assert "items" in data_q
    assert len(data_q["items"]) > 0
    assert any(hit["lemma"] == "bank" for hit in data_q["items"])

    # Search with query parameter (frontend convention)
    res_query = await client.get("/v1/words:search", params={"query": "bank"})
    assert res_query.status_code == 200
    data_query = res_query.json()
    assert len(data_query["items"]) > 0

    # Missing both q and query -> 422
    res_empty = await client.get("/v1/words:search")
    assert res_empty.status_code == 422
    assert res_empty.json()["error"] == "invalid_lexical_query"

    # Whitespace only -> 422
    res_ws = await client.get("/v1/words:search", params={"query": "   "})
    assert res_ws.status_code == 422
    assert res_ws.json()["error"] == "invalid_lexical_query"


async def test_vocabulary_batch_preview(app_client):
    """POST /v1/words:batchPreview: batch preview words -> 200."""
    client = app_client.client

    response = await client.post(
        "/v1/words:batchPreview",
        json={"word_ids": [app_client.word_id]},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["word_id"] == app_client.word_id
    assert data[0]["lemma"] == "bank"
    assert len(data[0]["senses"]) >= 1

    # Malformed payload -> 422
    invalid_res = await client.post(
        "/v1/words:batchPreview",
        json={"word_ids": "invalid-type"},
    )
    assert invalid_res.status_code == 422
    assert invalid_res.json()["error"] == "invalid_request"


# ---------------------------------------------------------------------------
# 4. Study HTTP Endpoints
# ---------------------------------------------------------------------------


async def test_study_progress_summary(app_client):
    """GET /v1/study/progress: progress summary -> 200."""
    client = app_client.client
    headers = app_client.headers

    # Missing authorization token -> 401
    unauth = await client.get("/v1/study/progress")
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.get("/v1/study/progress", headers={"Authorization": "Bearer bad-token"})
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"

    # Overall progress
    response = await client.get("/v1/study/progress", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "studied" in data
    assert "due" in data
    assert "new" in data
    assert "not_due" in data

    # Node-scoped progress
    personal_id = app_client.roots[NodeRole.PERSONAL_ROOT].id
    node_response = await client.get(
        "/v1/study/progress",
        headers=headers,
        params={"node_id": str(personal_id)},
    )
    assert node_response.status_code == 200
    node_data = node_response.json()
    assert "total" in node_data

    # Strict query params check: unexpected query param -> 422
    res_strict = await client.get(
        "/v1/study/progress",
        headers=headers,
        params={"unexpected_filter": "123"},
    )
    assert res_strict.status_code == 422
    assert res_strict.json()["error"] == "invalid_query_parameters"


async def test_study_activity_events(app_client):
    """GET /v1/study/activity: daily activity events -> 200."""
    client = app_client.client
    headers = app_client.headers

    # Missing authorization token -> 401
    unauth = await client.get("/v1/study/activity")
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.get("/v1/study/activity", headers={"Authorization": "Bearer bad-token"})
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"

    # Default activity window
    response = await client.get("/v1/study/activity", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "current_streak" in data
    assert "longest_streak" in data
    assert "practice_events" in data
    assert "days" in data
    assert isinstance(data["days"], list)

    # Date range filtered activity window
    range_response = await client.get(
        "/v1/study/activity",
        headers=headers,
        params={"start_date": "2026-01-01", "end_date": "2026-01-10"},
    )
    assert range_response.status_code == 200
    range_data = range_response.json()
    assert len(range_data["days"]) == 10

    # Strict query params check: unexpected query param -> 422
    res_strict = await client.get(
        "/v1/study/activity",
        headers=headers,
        params={"unexpected_param": "foo"},
    )
    assert res_strict.status_code == 422
    assert res_strict.json()["error"] == "invalid_query_parameters"


async def test_study_review_schedule_intervals(app_client):
    """GET /v1/study/review-schedule: review schedule intervals -> 200."""
    client = app_client.client
    headers = app_client.headers

    # Missing authorization token -> 401
    unauth = await client.get("/v1/study/review-schedule")
    assert unauth.status_code == 401
    assert unauth.json()["error"] == "authentication_required"

    # Invalid bearer token -> 401
    bad_auth = await client.get(
        "/v1/study/review-schedule", headers={"Authorization": "Bearer bad-token"}
    )
    assert bad_auth.status_code == 401
    assert bad_auth.json()["error"] == "invalid_credentials"

    # Review schedule
    response = await client.get("/v1/study/review-schedule", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "timezone" in data
    assert "start_date" in data
    assert "days" in data
    assert isinstance(data["days"], list)

    # Strict query params check: unexpected query param -> 422
    res_strict = await client.get(
        "/v1/study/review-schedule",
        headers=headers,
        params={"unexpected_param": "bar"},
    )
    assert res_strict.status_code == 422
    assert res_strict.json()["error"] == "invalid_query_parameters"
