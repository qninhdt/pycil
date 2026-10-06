import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, func, select
from starlette.requests import Request

from pycil.account.auth import ActorContext, actor, bearer
from pycil.account.models import UsagePeriod, User
from pycil.account.plans import Feature, Plan
from pycil.account.usage import admit, change_plan, settle
from pycil.dependencies import process_resources
from pycil.http import Problem
from pycil.main import create_app


async def test_admission_is_readonly_and_upgrade_downgrade_preserve_usage(database, user, config):
    _, sessions, _ = database
    moment = datetime.now(UTC)
    async with sessions() as session:
        assert await admit(session, user.id, config, Feature.ASSISTANT, moment) is Plan.FREE
        assert await session.scalar(select(func.count()).select_from(UsagePeriod)) == 0
    async with sessions() as session:
        await settle(
            session,
            user.id,
            config,
            execution_key=uuid4(),
            feature=Feature.ASSISTANT,
            units=1_000_000,
            unmetered_calls=0,
            moment=moment,
        )
    async with sessions() as session:
        with pytest.raises(Problem, match="allowance_exhausted"):
            await admit(session, user.id, config, Feature.ASSISTANT, moment)
        await change_plan(session, user.id, Plan.PRO, config, moment)
        await change_plan(session, user.id, Plan.FREE, config, moment)
        period = await session.scalar(select(UsagePeriod))
        assert (period.allowance_units, period.used_units) == (10_000_000, 1_000_000)


async def test_settlement_conflict_and_missing_usage_are_not_invented(database, user, config):
    _, sessions, _ = database
    key = uuid4()
    async with sessions() as session:
        await settle(
            session,
            user.id,
            config,
            execution_key=key,
            feature=Feature.ASSISTANT,
            units=0,
            unmetered_calls=1,
            moment=datetime.now(UTC),
        )
        with pytest.raises(Problem, match="usage_event_conflict"):
            await settle(
                session,
                user.id,
                config,
                execution_key=key,
                feature=Feature.ASSISTANT,
                units=1,
                unmetered_calls=1,
                moment=datetime.now(UTC),
            )
        assert await session.scalar(select(UsagePeriod.used_units)) == 0


async def test_clerk_failure_prevents_provision_and_removal_routes_are_absent(
    database, user, deployment, config, no_inference
):
    async with process_resources(config, deployment) as resources:
        subject = "missing-" + uuid4().hex

        async def identity(token):
            return subject

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(503))
        ) as http:
            state = SimpleNamespace(
                **(
                    vars(resources)
                    | {
                        "http": http,
                        "deployment": deployment,
                        "identity": SimpleNamespace(subject=identity),
                    }
                )
            )
            request = Request(
                {
                    "type": "http",
                    "headers": [(b"authorization", b"Bearer test")],
                    "app": SimpleNamespace(state=state),
                }
            )
            with pytest.raises(Problem, match="identity_service_unavailable"):
                async with resources.sessions() as session:
                    await actor(request, session, await bearer(request))
        async with resources.sessions() as session:
            assert await session.get(User, user.id) is not None
            assert await session.scalar(select(User).where(User.clerk_subject == subject)) is None
    paths = create_app().openapi()["paths"]
    assert "delete" not in paths["/v1/me"]
    assert "/v1/me/export" not in paths


async def test_concurrent_provisioning_is_idempotent_without_account_lock(
    database, user, deployment, config, no_inference
):
    async with process_resources(config, deployment) as resources:
        subject = "new-" + uuid4().hex

        async def identity(token):
            return subject

        def clerk(request):
            assert request.method == "GET"
            return httpx.Response(200)

        async with httpx.AsyncClient(transport=httpx.MockTransport(clerk)) as http:
            state = SimpleNamespace(
                **(
                    vars(resources)
                    | {
                        "http": http,
                        "deployment": deployment,
                        "identity": SimpleNamespace(subject=identity),
                    }
                )
            )
            request = Request(
                {
                    "type": "http",
                    "headers": [(b"authorization", b"Bearer test")],
                    "app": SimpleNamespace(state=state),
                }
            )

            async def provision():
                async with resources.sessions() as session:
                    return await actor(request, session, await bearer(request))

            results = await asyncio.gather(*(provision() for _ in range(4)))
            assert len({result.id for result in results}) == 1
            assert results[0].id.version == 7
        async with resources.sessions() as session:
            assert await session.get(User, user.id) is not None
            assert (
                await session.scalar(
                    select(func.count()).select_from(User).where(User.clerk_subject == subject)
                )
                == 1
            )


async def test_actor_cache_detached_hits_jwt_gate_outage_and_fresh_entitlements(
    database, user, deployment, config, no_inference, monkeypatch
):
    from redis.exceptions import ConnectionError

    _, sessions, _ = database
    async with process_resources(config, deployment) as resources:
        verified = []

        async def subject(token):
            verified.append(token)
            if token != "verified":
                raise Problem(401, "invalid_credentials")
            return user.clerk_subject

        state = SimpleNamespace(
            **(
                vars(resources)
                | {
                    "deployment": deployment,
                    "identity": SimpleNamespace(subject=subject),
                }
            )
        )

        def request(token="verified"):
            return Request(
                {
                    "type": "http",
                    "headers": [(b"authorization", ("Bearer " + token).encode())],
                    "app": SimpleNamespace(state=state),
                }
            )

        async with resources.sessions() as session:
            cold = await actor(request(), session, await bearer(request()))
        assert isinstance(cold, ActorContext) and not isinstance(cold, User)
        assert cold.settings == {}
        cold.settings["learning"] = {"formats": ["SINGLE_WORD"]}
        queries = []

        def capture(_conn, _cursor, statement, *_):
            queries.append(statement)

        event.listen(resources.engine.sync_engine, "before_cursor_execute", capture)
        try:
            async with resources.sessions() as session:
                warm = await actor(request(), session, await bearer(request()))
            assert warm.id == cold.id and warm.settings == {}
            assert queries == []
            assert len(verified) == 2
            with pytest.raises(Problem, match="invalid_credentials"):
                async with resources.sessions() as session:
                    await actor(request("invalid"), session, await bearer(request("invalid")))
            assert len(verified) == 3 and queries == []
        finally:
            event.remove(resources.engine.sync_engine, "before_cursor_execute", capture)

        async with resources.sessions() as session:
            await change_plan(session, user.id, Plan.PRO, config, datetime.now(UTC))
        assert await resources.cache.get(f"actor:v2:{user.clerk_subject}", ActorContext) is None
        async with resources.sessions() as session:
            pro = await actor(request(), session, await bearer(request()))
        assert pro.plan is Plan.PRO
        # Simulate a missed invalidation in another writer: privileged routes must
        # consult PostgreSQL, not the stale context. No new cache coordination.
        async with sessions() as session:
            await change_plan(session, user.id, Plan.FREE, config, datetime.now(UTC))
        assert (
            await resources.cache.get(f"actor:v2:{user.clerk_subject}", ActorContext)
        ).plan is Plan.PRO
        app = create_app()
        for name, value in vars(state).items():
            setattr(app.state, name, value)
        app.state.product = config
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer verified"},
        ) as client:
            denied = await client.post(
                "/v1/study/grade",
                json={
                    "question_id": 123,
                    "format": "SINGLE_WORD",
                    "answer": "bank",
                },
            )
            assert denied.status_code == 403
            assert (await client.get("/v1/me/usage")).json()["allowance_units"] == 1_000_000
        assert await resources.redis.ttl(resources.cache.key(f"actor:v2:{user.clerk_subject}")) > 0

        async def unavailable(*args, **kwargs):
            raise ConnectionError("cache unavailable")

        monkeypatch.setattr(resources.redis, "get", unavailable)
        monkeypatch.setattr(resources.redis, "eval", unavailable)
        async with resources.sessions() as session:
            fallback = await actor(request(), session, await bearer(request()))
        assert fallback.id == user.id and fallback.plan is Plan.FREE
