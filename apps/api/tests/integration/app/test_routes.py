from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from pycil.account.models import User
from pycil.account.plans import Plan
from pycil.app.config import load_config
from pycil.app.factory import create_app
from pycil.library.models import Node
from pycil.study.artifacts.schemas import Artifact
from pycil.study.artifacts.storage import append
from pycil.study.enums import QuestionArtifactType
from pycil.study.models import UserSense
from pycil.vocabulary.errors import InvalidOutputError
from tests.support.account import account
from tests.support.artifacts import payloads
from tests.support.vocabulary import neutral_word


class Identity:
    def __init__(self, subject):
        self.value = subject

    async def subject(self, token):
        return self.value


async def test_study_http_grading_rechecks_plan_and_review_header_controls_replay(database):
    user, _ = await account(database.sessions)
    async with database.sessions() as session, session.begin():
        saved_user = await session.get(User, user.id)
        saved_user.display_name, saved_user.handle = "Alice", "alice"
    _, sense_id = await neutral_word(database.sessions)
    saved = await append(
        database.sessions,
        [
            Artifact(
                id=0,
                sense_id=sense_id,
                theme_id=None,
                artifact_type=QuestionArtifactType.WORD_DEFINITION,
                payload=payloads()[QuestionArtifactType.WORD_DEFINITION],
            )
        ],
    )
    app = create_app()
    app.state.sessions = database.sessions
    app.state.product = load_config()
    app.state.identity = Identity(user.clerk_subject)
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    app.state.search = app.state.artifact_cache = None

    class FailedProvider:
        async def decide(self, *args, **kwargs):
            raise InvalidOutputError("private-provider-marker")

    app.state.decision_llm = FailedProvider()
    headers = {"Authorization": "Bearer controlled-identity"}
    request = dict(
        question_artifact_id=saved[0].id,
        question_type="definition_to_word",
        format="single_word",
        answer="bank",
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as client:
        denied = await client.post("/v1/study:grade", headers=headers, json=request)
        assert (
            denied.status_code == 403 and denied.json()["error"] == "advanced_grading_not_available"
        )
        async with database.sessions() as session, session.begin():
            (await session.get(User, user.id)).plan = Plan.PRO
        graded = await client.post("/v1/study:grade", headers=headers, json=request)
        assert graded.status_code == 200
        assert graded.json() == {
            key: value for key, value in request.items() if key != "answer"
        } | {
            "diagnostics": {"task_fit": True, "spelling_error": False, "sense_id": sense_id},
        }
        missing = await client.post(
            "/v1/study:grade",
            headers=headers,
            json=request | {"question_artifact_id": saved[0].id + 100},
        )
        assert (
            missing.status_code == 404 and missing.json()["error"] == "question_artifact_not_found"
        )
        unavailable = await client.post(
            "/v1/study:grade", headers=headers, json=request | {"answer": "lender"}
        )
        assert (
            unavailable.status_code == 503 and unavailable.json()["error"] == "grading_unavailable"
        )
        assert "private-provider-marker" not in unavailable.text
        batch = {
            "results": [
                graded.json()
                | {
                    "answered_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                }
            ]
        }
        no_key = await client.post("/v1/study:submitResults", headers=headers, json=batch)
        assert no_key.status_code == 422
        keyed = headers | {"Idempotency-Key": str(uuid4())}
        first = await client.post("/v1/study:submitResults", headers=keyed, json=batch)
        replay = await client.post("/v1/study:submitResults", headers=keyed, json=batch)
        assert first.status_code == replay.status_code == 200 and first.json() == replay.json()
        conflict = await client.post(
            "/v1/study:submitResults",
            headers=keyed,
            json={
                "results": [
                    batch["results"][0]
                    | {
                        "diagnostics": {
                            "task_fit": False,
                            "spelling_error": False,
                            "sense_id": None,
                        }
                    },
                ]
            },
        )
        assert conflict.status_code == 409 and conflict.json()["error"] == "review_batch_conflict"
    async with database.sessions() as session:
        assert (await session.get(UserSense, (user.id, sense_id))).review_count == 1


async def test_http_routes_enforce_auth_validate_enums_and_persist_domain_mutations(database):
    user, _ = await account(database.sessions)
    async with database.sessions() as session, session.begin():
        saved = await session.get(User, user.id)
        saved.display_name, saved.handle = "Alice", "alice"
    app = create_app()
    app.state.sessions = database.sessions
    app.state.product = load_config()
    app.state.identity = Identity(user.clerk_subject)
    app.state.deployment = SimpleNamespace(allowed_origins=[])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as client:
        assert (await client.get("/v1/me")).status_code == 401
        headers = {"Authorization": "Bearer controlled-identity"}
        me = await client.get("/v1/me", headers=headers)
        assert me.status_code == 200 and me.json()["plan"] == "free"
        invalid = await client.post(
            "/v1/nodes", headers=headers, json={"type": "DECK", "name": "Wrong enum"}
        )
        assert invalid.status_code == 422
        created = await client.post(
            "/v1/nodes", headers=headers, json={"type": "deck", "name": "Finance"}
        )
        assert created.status_code == 201
        node = created.json()
        assert node["type"] == "deck" and node["space"] == "personal"
        updated = await client.patch(
            f"/v1/nodes/{node['id']}", headers=headers, json={"description": "saved"}
        )
        assert updated.status_code == 200 and updated.json()["description"] == "saved"
        public = await client.get(f"/v1/users/{user.id}")
        assert public.status_code == 200
        assert "settings" not in public.json() and "clerk_subject" not in public.json()
    async with database.sessions() as session:
        stored = await session.scalar(select(Node).where(Node.name == "Finance"))
        assert stored.description == "saved"


async def test_request_query_timeout_is_sanitized_and_closes_failed_session(database):
    from sqlalchemy import text

    from pycil.app.dependencies import Session

    app = create_app()
    app.state.sessions = database.sessions
    app.state.product = load_config()
    app.state.deployment = SimpleNamespace(allowed_origins=[])

    @app.get("/test-query-timeout")
    async def timed(session: Session):
        await session.execute(text("SET LOCAL statement_timeout = '10ms'"))
        await session.execute(text("SELECT pg_sleep(1)"))
        return {"unexpected": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://api.test") as client:
        response = await client.get("/test-query-timeout")
        assert response.status_code == 503
        assert response.json()["error"] == "query_timeout"
        assert "pg_sleep" not in response.text
        assert response.headers["x-request-id"]
    assert database.engine.pool.checkedout() == 0
    async with database.sessions() as session:
        assert await session.scalar(text("SELECT 1")) == 1
