import asyncio
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from pycil.account.models import User
from pycil.dependencies import process_resources
from pycil.main import create_app


async def test_preferences_route_persists_jsonb_without_lost_updates(
    user, config, deployment, no_inference
):
    async with process_resources(config, deployment) as resources:
        sessions = resources.sessions
        app = create_app()
        for name, value in vars(resources).items():
            setattr(app.state, name, value)
        app.state.product = config

        async def subject(token):
            return user.clerk_subject

        app.state.identity = SimpleNamespace(subject=subject)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer verified"},
        ) as client:
            before = await client.get("/v1/me")
            assert before.status_code == 200
            assert before.json()["settings"]["learning"]["questions_per_sense"] == 2
            assert before.json()["settings"]["assistant"] == {"auto_approve": False}
            async with sessions() as session:
                persisted = await session.get(User, user.id)
                assert persisted.settings == {}
            responses = await asyncio.gather(
                client.patch("/v1/me/settings", json={"locale": "vi"}),
                client.patch("/v1/me/settings", json={"learning": {"max_sense_count": 12}}),
            )
            assert [r.status_code for r in responses] == [200, 200]
            refreshed = (await client.get("/v1/me")).json()
            assert refreshed["settings"]["locale"] == "vi"
            assert refreshed["settings"]["learning"]["max_sense_count"] == 12
            async with sessions() as session:
                persisted = await session.scalar(select(User).where(User.id == user.id))
                assert persisted.settings == {"locale": "vi", "learning": {"max_sense_count": 12}}
            assert (await client.patch("/v1/me/settings", json={"plan": "PRO"})).status_code == 422
            denied = await client.patch(
                "/v1/me/settings", json={"learning": {"formats": ["SHORT_ANSWER"]}}
            )
            assert denied.status_code == 403
            assert (await client.get("/v1/me/settings")).status_code == 405
            changed = await client.patch(
                "/v1/me/settings", json={"assistant": {"auto_approve": True}}
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["settings"]["assistant"]["auto_approve"] is True
            assert changed.json()["settings"]["learning"]["max_sense_count"] == 12
            assert (await client.get("/v1/me")).json()["settings"]["assistant"][
                "auto_approve"
            ] is True
            for invalid in [
                None,
                {"auto_approve": None},
                {"auto_approve": "true"},
                {"auto_approve": 1},
                {"unknown": True},
            ]:
                assert (
                    await client.patch("/v1/me/settings", json={"assistant": invalid})
                ).status_code == 422
            async with sessions() as session, session.begin():
                persisted = await session.get(User, user.id)
                persisted.settings = {
                    "learning": {
                        "question_types": ["DEFINITION_TO_WORD"],
                        "formats": ["SINGLE_WORD"],
                    }
                }
            changed = await client.patch(
                "/v1/me/settings", json={"learning": {"question_types": ["MEANING_IN_CONTEXT"]}}
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["settings"]["learning"]["formats"] == ["SINGLE_WORD"]
            assert changed.json()["effective_learning"]["formats"] == ["SINGLE_CHOICE"]
            refreshed = await client.get("/v1/me")
            assert refreshed.status_code == 200, refreshed.text
            assert refreshed.json()["effective_learning"]["question_types"] == [
                "MEANING_IN_CONTEXT"
            ]


async def test_missing_and_invalid_authentication_are_not_anonymous(database, config):
    _, sessions, _ = database
    app = create_app()
    app.state.sessions = sessions
    app.state.product = config
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/v1/me")
        assert missing.status_code == 401
        assert missing.json() == {"error": "authentication_required"}
        invalid = await client.get("/v1/me", headers={"Authorization": "Basic invalid"})
        assert invalid.status_code == 401
        assert invalid.json() == {"error": "invalid_credentials"}
