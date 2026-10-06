"""Real-store end-to-end contracts; no provider calls or frontend mocks."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import delete, event, func, select, text, update

from pycil.account.auth import actor, optional_actor
from pycil.account.models import User
from pycil.dependencies import process_resources
from pycil.http import Problem
from pycil.library.models import Node, NodePath, NodeRole, NodeSpace
from pycil.library.nodes import create_node, delete_node, save_node
from pycil.library.schemas import NodeCreate, NodeSave
from pycil.library.scope import ScopeBudget
from pycil.library.tree import provision_library, roots
from pycil.main import create_app
from pycil.study import reviews
from pycil.study.models import DailyActivity, ReviewReceipt, UserSense
from pycil.study.progress import summaries
from pycil.study.schemas import ReviewBatch


@pytest.mark.parametrize(
    "instant",
    [
        "2026-03-08T06:59:59+00:00",
        "2026-03-08T07:00:00+00:00",
        "2026-11-01T05:59:59+00:00",
        "2026-11-01T06:00:00+00:00",
        "2026-10-06T03:59:59+00:00",
        "2026-10-06T04:00:00+00:00",
    ],
)
async def test_accepted_day_dst_midnight_and_timezone_replay(
    database,
    user,
    senses,
    config,
    monkeypatch,
    instant,
):
    _, sessions, _ = database
    now = datetime.fromisoformat(instant)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(reviews, "datetime", Clock)
    async with sessions() as session, session.begin():
        (await session.get(User, user.id)).settings = {"timezone": "America/New_York"}
    key = uuid4()
    body = ReviewBatch(results=[{"sense_id": 1, "rating": "AGAIN"}])
    async with sessions() as session:
        saved = await reviews.review(session, user.id, body, key, config)
    assert saved["activity_day"] == now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    async with sessions() as session, session.begin():
        (await session.get(User, user.id)).settings = {"timezone": "Pacific/Kiritimati"}
    now += timedelta(days=1)
    async with sessions() as session:
        assert await reviews.review(session, user.id, body, key, config) == saved
        assert await session.scalar(select(func.count()).select_from(DailyActivity)) == 1


async def test_assistant_read_tools_share_authorized_services(
    resources,
    database,
    user,
    senses,
    config,
):
    from pycil.assistant.tools import tools

    deck = await make_node(database[1], user, config, type="DECK", name="bank", sense_ids=[1, 2])
    available = {tool.name: tool for tool in tools(resources, user, config)}
    assert {"search_nodes", "sense_context"} <= available.keys()
    async with database[1]() as session:
        personal = (await roots(session, user.id))[NodeRole.PERSONAL_ROOT].id
    result = await available["search_nodes"].ainvoke({"query": "bank", "node_id": str(personal)})
    assert [node["id"] for node in result["nodes"]] == [deck["id"]]
    context = await available["sense_context"].ainvoke({"sense_ids": [1, 2]})
    assert (context["new"], context["total"]) == (2, 2)
    assert context["senses"][0]["deck_count"] == 1
    assert not {"review", "edit_profile", "star_node"} & available.keys()


async def test_search_vector_weights_updates_and_authoritative_paths(
    resources,
    database,
    user,
    config,
):
    sessions = database[1]
    title = await publish(sessions, user, config, type="FOLDER", name="needle")
    description = await publish(
        sessions, user, config, type="FOLDER", name="other", description="needle"
    )
    private = await make_node(sessions, user, config, type="FOLDER", name="needle private")
    async with sessions() as session, session.begin():
        await session.execute(
            update(Node).where(Node.id == private["id"]).values(space=NodeSpace.PUBLISHED)
        )
    async with client_for(resources, config, user) as client:
        result = (await client.get("/v1/discovery/nodes", params={"q": "needle"})).json()
        assert [node["id"] for node in result["nodes"]] == [
            str(title["id"]),
            str(description["id"]),
        ]
        assert all(node["parent_id"] is not None for node in result["nodes"])
        rejected = await client.get("/v1/discovery/nodes", params={"q": "x" * 201})
        assert rejected.status_code == 422
    async with sessions() as session:
        await save_node(
            session,
            user.id,
            title["id"],
            NodeSave(name="Động từ", description="updated token", parent_id=title["parent_id"]),
            config,
        )
    async with client_for(resources, config, None) as guest:
        result = (await guest.get("/v1/discovery/nodes", params={"q": "needle"})).json()
        assert [node["id"] for node in result["nodes"]] == [str(description["id"])]
        result = (await guest.get("/v1/discovery/nodes", params={"q": "Động"})).json()
        assert [node["id"] for node in result["nodes"]] == [str(title["id"])]
        denied = await guest.post(
            "/v1/study/summaries", json={"node_ids": [str(title["id"]), str(private["id"])]}
        )
        assert denied.status_code == 404 and "total" not in denied.json()


async def test_discovery_cursor_skips_unreadable_candidate_batches(resources, user, config):
    sessions = resources.sessions
    older = await publish(sessions, user, config, type="FOLDER", name="older")
    private_ids = [
        (await make_node(sessions, user, config, type="FOLDER", name=f"hidden-{i}"))["id"]
        for i in range(51)
    ]
    newer = await publish(sessions, user, config, type="FOLDER", name="newer")
    async with sessions() as session, session.begin():
        await session.execute(
            update(Node).where(Node.id.in_(private_ids)).values(space=NodeSpace.PUBLISHED)
        )
    async with client_for(resources, config, None) as guest:
        first = (await guest.get("/v1/discovery/nodes", params={"limit": 1})).json()
        assert [node["id"] for node in first["nodes"]] == [str(newer["id"])]
        assert first["next_cursor"]
        second = (
            await guest.get(
                "/v1/discovery/nodes",
                params={"limit": 1, "cursor": first["next_cursor"]},
            )
        ).json()
        assert [node["id"] for node in second["nodes"]] == [str(older["id"])]
        assert second["next_cursor"] is None


async def test_native_examples_batched_and_explicit_read_windows(
    resources,
    database,
    user,
    senses,
    config,
):
    async with database[0].begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO lexi.examples(sense_id,content) "
                "VALUES(1,'First native example'),(1,'Second native example'),"
                "(1,'Third native example')"
            )
        )
    deck = await make_node(database[1], user, config, type="DECK", name="bank", sense_ids=senses)
    async with client_for(resources, config, user) as client:
        word = (await client.post("/v1/words/previews", json={"word_ids": [1]})).json()[0]
        assert len(word["senses"][0]["examples"]) == 2
        page = (
            await client.get(f"/v1/nodes/{deck['id']}/senses", params={"include": "examples"})
        ).json()
        assert len(page["senses"][0]["examples"]) == 2
        for path, params in (
            ("/v1/study/progress", {"history_days": 30}),
            ("/v1/study/activity", {"start_date": "2024-01-01"}),
            ("/v1/study/activity", {"start_date": "2024-01-01", "end_date": "2025-01-01"}),
            ("/v1/study/review-schedule", {"start_date": "2024-01-01", "end_date": "2024-01-02"}),
        ):
            assert (await client.get(path, params=params)).status_code == 422
        leap = await client.get(
            "/v1/study/activity", params={"start_date": "2024-01-01", "end_date": "2024-12-31"}
        )
        assert leap.status_code == 200 and len(leap.json()["days"]) == 366
        assert leap.json()["applied_events"] == leap.json()["practice_events"] == 0


async def test_over_limit_owner_can_repair_without_growth(database, user, senses, config):
    sessions = database[1]
    folder = await make_node(sessions, user, config, type="FOLDER", name="nested")
    deck = await make_node(
        sessions, user, config, type="DECK", name="old", sense_ids=senses, parent_id=folder["id"]
    )
    limited = config.model_copy(
        update={
            "library": config.library.model_copy(
                update={
                    "max_owned_nodes": 1,
                    "max_owned_memberships": 1,
                    "max_senses_per_deck": 1,
                    "max_depth": 1,
                }
            )
        }
    )
    async with sessions() as session:
        renamed = await save_node(
            session,
            user.id,
            deck["id"],
            NodeSave(name="renamed", parent_id=folder["id"], sense_ids=senses),
            limited,
        )
        assert renamed["sense_ids"] == senses
    async with sessions() as session:
        repaired = await save_node(
            session, user.id, deck["id"], NodeSave(name="repaired", sense_ids=[1]), limited
        )
        assert repaired["sense_ids"] == [1]
    async with sessions() as session:
        with pytest.raises(Problem, match="deck_sense_limit_exceeded"):
            await save_node(
                session,
                user.id,
                deck["id"],
                NodeSave(name="invalid growth", sense_ids=senses),
                limited,
            )
    async with sessions() as session:
        with pytest.raises(Problem, match="quota_exceeded"):
            await create_node(session, user.id, NodeCreate(type="FOLDER", name="new"), limited)


async def test_inline_search_reuses_scope_work_and_deadline(database, user, senses, config):
    from pycil.library.search import search_nodes

    engine, sessions, _ = database
    folder = await make_node(sessions, user, config, type="FOLDER", name="parent")
    await make_node(
        sessions, user, config, type="DECK", name="bank", sense_ids=senses, parent_id=folder["id"]
    )
    statements = []

    def capture(_connection, _cursor, statement, *_):
        if "node_paths.ancestor_id IN" in statement:
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        async with sessions() as session:
            result = await search_nodes(
                session, user.id, config, node_id=folder["id"], q="bank", include="summary"
            )
            assert result["nodes"][0]["summary"]["total"] == 2
        # Only the original search scope expands the physical closure. Summary
        # authorization still runs, but reuses its frontier/membership projection.
        assert len(statements) == 1
        expired = ScopeBudget(user.id, started_at=0)
        async with sessions() as session:
            with pytest.raises(Problem, match="scope_timeout"):
                await summaries(session, user.id, config, [folder["id"]], budget=expired)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)


async def test_physical_closure_matches_parent_walk_oracle(database, user, senses, config):
    sessions = database[1]

    async def check():
        async with sessions() as session:
            parents = dict(
                (
                    await session.execute(
                        select(Node.id, Node.parent_id).where(
                            Node.owner_id == user.id, Node.deleted_at.is_(None)
                        )
                    )
                ).all()
            )
            actual = set(
                (
                    await session.execute(
                        select(NodePath.ancestor_id, NodePath.descendant_id, NodePath.depth)
                    )
                ).all()
            )
        expected = set()
        for descendant in parents:
            ancestor, depth, seen = descendant, 0, set()
            while ancestor is not None:
                assert ancestor not in seen and ancestor in parents
                seen.add(ancestor)
                expected.add((ancestor, descendant, depth))
                ancestor, depth = parents[ancestor], depth + 1
        assert actual == expected

    a, b, c = [
        await make_node(sessions, user, config, type="FOLDER", name=name)
        for name in ("a", "b", "c")
    ]
    nested = await make_node(
        sessions, user, config, type="FOLDER", name="nested", parent_id=a["id"]
    )
    await make_node(
        sessions, user, config, type="DECK", name="deck", parent_id=nested["id"], sense_ids=senses
    )
    await make_node(
        sessions,
        user,
        config,
        type="REFERENCE",
        name="alias",
        parent_id=c["id"],
        reference_id=a["id"],
    )
    await check()
    for node, parent in ((nested, b), (b, c), (a, b)):
        async with sessions() as session:
            await save_node(
                session,
                user.id,
                node["id"],
                NodeSave(name=node["name"], parent_id=parent["id"]),
                config,
            )
        await check()
    async with sessions() as session:
        public = (await roots(session, user.id))[NodeRole.PUBLISHED_ROOT].id
        await session.rollback()
        await save_node(
            session,
            user.id,
            c["id"],
            NodeSave(name="public", parent_id=public, confirm_publication=True),
            config,
        )
    await check()
    async with sessions() as session:
        await delete_node(session, user.id, b["id"], config)
    await check()


async def test_account_delete_cascades_learning_receipts_activity(database, user, senses, config):
    sessions = database[1]
    body = ReviewBatch(results=[{"sense_id": 1, "rating": "GOOD"}])
    async with sessions() as session:
        await reviews.review(session, user.id, body, uuid4(), config)
    async with sessions() as session, session.begin():
        await session.execute(delete(User).where(User.id == user.id))
    async with sessions() as session:
        for model in (UserSense, ReviewReceipt, DailyActivity):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        await session.rollback()
        with pytest.raises(Problem, match="account_not_found"):
            await reviews.review(session, user.id, body, uuid4(), config)


@pytest.fixture
async def resources(deployment, config, no_inference):
    async with process_resources(config, deployment) as value:
        yield value


@asynccontextmanager
async def client_for(resources, config, user):
    app = create_app()
    for name, value in vars(resources).items():
        setattr(app.state, name, value)
    app.state.product = config

    async def authenticated():
        if user is None:
            raise Problem(401, "authentication_required")
        return user

    async def viewer():
        return user

    app.dependency_overrides[actor] = authenticated
    app.dependency_overrides[optional_actor] = viewer
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def make_node(sessions, user, config, **values):
    async with sessions() as session:
        return await create_node(session, user.id, NodeCreate(**values), config)


async def publish(sessions, user, config, **values):
    async with sessions() as session:
        system = await roots(session, user.id)
    return await make_node(
        sessions,
        user,
        config,
        parent_id=system[NodeRole.PUBLISHED_ROOT].id,
        confirm_publication=True,
        **values,
    )


async def test_batch_atomic_rollback_replay_and_cross_day(
    database, user, senses, config, monkeypatch
):
    _, sessions, _ = database
    now = datetime(2026, 10, 6, 23, 59, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(reviews, "datetime", Clock)
    data = ReviewBatch(
        results=[{"sense_id": 2, "rating": "GOOD"}, {"sense_id": 1, "rating": "AGAIN"}]
    )
    original = reviews.next_state
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected")
        return original(*args)

    monkeypatch.setattr(reviews, "next_state", fail_second)
    async with sessions() as session:
        with pytest.raises(RuntimeError, match="injected"):
            await reviews.review(session, user.id, data, uuid4(), config)
        for model in (UserSense, ReviewReceipt, DailyActivity):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
    monkeypatch.setattr(reviews, "next_state", original)
    key = uuid4()

    async def send(body=data, event_key=key):
        async with sessions() as session:
            return await reviews.review(session, user.id, body, event_key, config)

    first, replay = await asyncio.gather(send(), send())
    assert first == replay and [r["sense_id"] for r in first["results"]] == [2, 1]
    now += timedelta(days=2)
    async with sessions() as session, session.begin():
        (await session.get(User, user.id)).settings = {"timezone": "Asia/Ho_Chi_Minh"}
    await send(ReviewBatch(results=[{"sense_id": 1, "rating": "AGAIN"}]), uuid4())
    assert await send() == first
    with pytest.raises(Problem, match="review_batch_conflict"):
        await send(ReviewBatch(results=list(reversed(data.results))))
    with pytest.raises(Problem, match="sense_not_found"):
        await send(
            ReviewBatch(
                results=[{"sense_id": 1, "rating": "AGAIN"}, {"sense_id": 999999, "rating": "GOOD"}]
            ),
            uuid4(),
        )
    async with sessions() as session:
        assert await session.scalar(select(func.sum(DailyActivity.applied_events))) == 3
        assert await session.scalar(select(func.count()).select_from(ReviewReceipt)) == 2
        assert (await session.get(UserSense, (user.id, 1))).review_count == 2


async def test_overlapping_batches_sorted_locks(database, user, senses, config):
    _, sessions, _ = database

    async def send(ids):
        async with sessions() as session:
            return await reviews.review(
                session,
                user.id,
                ReviewBatch(results=[{"sense_id": i, "rating": "AGAIN"} for i in ids]),
                uuid4(),
                config,
            )

    async with asyncio.timeout(10):
        await asyncio.gather(send([1, 2]), send([2, 1]))
    async with sessions() as session:
        assert [
            (m.review_count, m.lapse_count)
            for m in (await session.scalars(select(UserSense))).all()
        ] == [(2, 1), (2, 1)]
        assert await session.scalar(select(func.sum(DailyActivity.applied_events))) == 4


async def test_profile_handle_concurrency_and_public_privacy(resources, user, config):
    sessions = resources.sessions
    async with sessions() as session, session.begin():
        other = User(clerk_subject="other-" + uuid4().hex, settings={})
        session.add(other)
        await session.flush()
        await provision_library(session, other.id)
    handle = "ninh_" + uuid4().hex[:10]
    async with client_for(resources, config, user) as a, client_for(resources, config, other) as b:
        responses = await asyncio.gather(
            a.patch(
                "/v1/me/profile", json={"handle": " " + handle.upper() + " ", "bio": " Hello "}
            ),
            b.patch("/v1/me/profile", json={"handle": handle}),
        )
        assert sorted(r.status_code for r in responses) == [200, 409]
        winner = next(r.json() for r in responses if r.status_code == 200)
        public = (await a.get("/v1/users/by-handle/" + handle)).json()
        assert public["id"] == winner["id"] and public["handle"] == handle
        assert set(public) == {
            "id",
            "display_name",
            "handle",
            "bio",
            "joined_at",
            "published_node_id",
        }
        assert (await a.patch("/v1/me/profile", json={"country": "VN"})).status_code == 422
        assert (await a.patch("/v1/me/profile", json={"handle": None})).status_code == 422
        assert (await a.patch("/v1/me/profile", json={"bio": None})).status_code == 200
        assert "pairs" in (await a.get("/v1/me")).json()["learning_options"]
    async with client_for(resources, config, None) as guest:
        assert (await guest.get("/v1/users/by-handle/" + handle)).status_code == 200
        assert (await guest.patch("/v1/me/profile", json={"bio": "x"})).status_code == 401


async def test_search_discovery_revoke_and_bound_cursors(resources, user, senses, config):
    sessions = resources.sessions
    private = await make_node(sessions, user, config, type="FOLDER", name="secret search")
    deck = await publish(
        sessions,
        user,
        config,
        type="DECK",
        name="English bank",
        description="financial practice",
        sense_ids=senses,
    )
    folder = await publish(sessions, user, config, type="FOLDER", name="English course")
    async with client_for(resources, config, None) as guest:
        page = (
            await guest.get(
                "/v1/discovery/nodes", params={"q": "English", "limit": 1, "include": "summary"}
            )
        ).json()
        assert len(page["nodes"]) == 1 and page["next_cursor"]
        assert page["nodes"][0]["summary"]["studied"] is None
        next_page = await guest.get(
            "/v1/discovery/nodes",
            params={"q": "English", "limit": 1, "cursor": page["next_cursor"]},
        )
        assert next_page.status_code == 200 and len(next_page.json()["nodes"]) == 1
        wrong = await guest.get(
            "/v1/discovery/nodes", params={"q": "financial", "cursor": page["next_cursor"]}
        )
        assert wrong.status_code == 422
        assert (await guest.get("/v1/discovery/nodes", params={"q": "secret"})).json()[
            "nodes"
        ] == []
        assert (
            len((await guest.get("/v1/discovery/nodes", params={"q": "financial"})).json()["nodes"])
            == 1
        )
        assert (
            await guest.get(f"/v1/nodes/{deck['id']}/search", params={"q": "bank"})
        ).status_code == 422
        async with sessions() as session:
            system = await roots(session, user.id)
            personal_id = system[NodeRole.PERSONAL_ROOT].id
            await session.rollback()
            await save_node(
                session,
                user.id,
                deck["id"],
                NodeSave(name=deck["name"], parent_id=personal_id, sense_ids=senses),
                config,
            )
        assert (await guest.get("/v1/discovery/nodes", params={"q": "bank"})).json()["nodes"] == []
        assert (await guest.get(f"/v1/nodes/{deck['id']}/senses")).status_code == 404
    async with client_for(resources, config, user) as owner:
        profile = (await owner.get("/v1/me")).json()
        page = (
            await owner.get(
                f"/v1/nodes/{profile['library_node_id']}/search", params={"q": "secret"}
            )
        ).json()
        assert page["nodes"][0]["id"] == str(private["id"])
        assert (
            await owner.get("/v1/nodes", params={"after_id": str(folder["id"])})
        ).status_code == 422


async def test_dictionary_context_sources_examples_and_sort(resources, user, senses, config):
    sessions = resources.sessions
    decks = [
        await make_node(sessions, user, config, type="DECK", name=f"deck-{i}", sense_ids=senses)
        for i in range(7)
    ]
    async with client_for(resources, config, user) as client:
        previews = await client.post("/v1/words/previews", json={"word_ids": [1]})
        assert previews.status_code == 200, previews.text
        assert len(previews.json()[0]["senses"]) == 2
        context = await client.get("/v1/me/words/1")
        assert context.status_code == 200, context.text
        assert context.json()["new"] == 2
        sense = context.json()["senses"][0]
        assert sense["deck_count"] == 7 and len(sense["decks"]) == 5 and sense["decks_has_more"]
        first = (await client.get("/v1/me/senses/1/decks", params={"limit": 5})).json()
        second = (
            await client.get(
                "/v1/me/senses/1/decks", params={"limit": 5, "cursor": first["next_cursor"]}
            )
        ).json()
        assert len(first["decks"]) + len(second["decks"]) == 7
        result = await client.get(
            f"/v1/nodes/{decks[0]['id']}/senses",
            params={"q": "BANK", "include": "sources,examples", "sort": "LEMMA_ASC", "limit": 1},
        )
        assert result.status_code == 200, result.text
        page = result.json()
        assert page["senses"][0]["source_count"] == 1
        next_page = (
            await client.get(
                f"/v1/nodes/{decks[0]['id']}/senses",
                params={
                    "q": "BANK",
                    "sort": "LEMMA_ASC",
                    "cursor": page["next_cursor"],
                    "limit": 1,
                },
            )
        ).json()
        assert next_page["as_of"] == page["as_of"]
        assert next_page["senses"][0]["sense_id"] != page["senses"][0]["sense_id"]
        assert (await client.get(f"/v1/nodes/{decks[0]['id']}/senses", params={"q": "%"})).json()[
            "senses"
        ] == []
        key = str(uuid4())
        body = {"results": [{"sense_id": 1, "rating": "GOOD"}]}
        assert (
            await client.post("/v1/study/reviews", json=body, headers={"Idempotency-Key": key})
        ).status_code == 200
        context = (await client.get("/v1/me/words/1")).json()
        assert context["studied"] == 1 and context["new"] == 1
        result = (
            await client.get(
                f"/v1/nodes/{decks[0]['id']}/senses",
                params={"sort": "LAST_REVIEWED_DESC", "limit": 1},
            )
        ).json()
        assert result["senses"][0]["sense_id"] == 1
        assert result["senses"][0]["learning"]["last_reviewed_at"]
        result = (
            await client.get(
                f"/v1/nodes/{decks[0]['id']}/senses",
                params={"sort": "LAST_REVIEWED_DESC", "limit": 1, "cursor": result["next_cursor"]},
            )
        ).json()
        assert result["senses"][0]["sense_id"] == 2
        assert result["senses"][0]["learning"]["last_reviewed_at"] is None


async def test_joint_summary_query_count_and_projection_budget(database, user, senses, config):
    engine, sessions, _ = database
    nodes = [
        await make_node(sessions, user, config, type="DECK", name=f"card-{i}", sense_ids=senses)
        for i in range(50)
    ]
    statements = []

    def capture(_connection, _cursor, statement, *_):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        counts = []
        for count in (5, 50):
            statements.clear()
            async with sessions() as session:
                result = await summaries(session, user.id, config, [n["id"] for n in nodes[:count]])
            counts.append(len(statements))
            assert len(result) == count and all(r["total"] == 2 for r in result)
            assert len({r["as_of"] for r in result}) == 1
        assert counts[0] == counts[1] and counts[1] <= 8
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    limited = config.model_copy(
        update={"library": config.library.model_copy(update={"max_scope_memberships": 3})}
    )
    async with sessions() as session:
        with pytest.raises(Problem, match="scope_too_large"):
            await summaries(session, user.id, limited, [n["id"] for n in nodes[:2]])


async def test_deleted_anchor_and_profile_rename(resources, user, config):
    sessions = resources.sessions
    folder = await make_node(sessions, user, config, type="FOLDER", name="parent")
    children = [
        await make_node(
            sessions, user, config, type="FOLDER", name=f"child-{i}", parent_id=folder["id"]
        )
        for i in range(3)
    ]
    async with client_for(resources, config, user) as client:
        first = (
            await client.get("/v1/nodes", params={"parent_id": str(folder["id"]), "limit": 1})
        ).json()
        assert first["next_cursor"]
        assert (await client.delete("/v1/nodes/" + first["nodes"][0]["id"])).status_code == 204
        second = await client.get(
            "/v1/nodes",
            params={"parent_id": str(folder["id"]), "limit": 1, "cursor": first["next_cursor"]},
        )
        assert second.status_code == 200 and second.json()["nodes"][0]["id"] == str(
            children[1]["id"]
        )
        wrong = await client.get(
            "/v1/nodes",
            params={"parent_id": str(children[2]["id"]), "cursor": first["next_cursor"]},
        )
        assert wrong.status_code == 422
        assert (
            await client.patch("/v1/me/profile", json={"handle": "old_handle"})
        ).status_code == 200
        assert (
            await client.patch("/v1/me/profile", json={"handle": "new_handle"})
        ).status_code == 200
        assert (await client.get("/v1/users/by-handle/old_handle")).status_code == 404
        assert (await client.get("/v1/users/by-handle/new_handle")).json()["handle"] == "new_handle"


async def test_direct_public_learning_tracking_and_live_context_revocation(
    resources, user, senses, config
):
    sessions = resources.sessions
    async with sessions() as session, session.begin():
        author = User(clerk_subject="author-" + uuid4().hex, settings={})
        session.add(author)
        await session.flush()
        await provision_library(session, author.id)
    public = await publish(
        sessions, author, config, type="DECK", name="author deck", sense_ids=senses
    )
    async with client_for(resources, config, user) as client:
        submitted = await client.post(
            "/v1/study/reviews",
            json={"results": [{"sense_id": 1, "rating": "GOOD"}]},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert submitted.status_code == 200
        assert (await client.get("/v1/study/progress")).json()["total"] == 0
        assert (await client.get("/v1/me/words/1")).json()["studied"] == 1
        reference = await make_node(
            sessions, user, config, type="REFERENCE", name="shortcut", reference_id=public["id"]
        )
        assert (await client.get("/v1/study/progress")).json()["studied"] == 1
        context = (await client.get("/v1/me/words/1")).json()
        assert (
            context["senses"][0]["deck_count"] == 1
            and not context["senses"][0]["decks"][0]["editable"]
        )
        async with sessions() as session:
            await save_node(
                session,
                author.id,
                public["id"],
                NodeSave(name=public["name"], sense_ids=senses),
                config,
            )
        assert (await client.get(f"/v1/nodes/{reference['id']}/senses")).json()["senses"] == []
        context = (await client.get("/v1/me/words/1")).json()
        assert context["studied"] == 1 and context["senses"][0]["deck_count"] == 0
        assert (await client.get("/v1/study/activity")).json()["applied_events"] == 1
        assert (await client.get("/v1/study/progress")).json()["total"] == 0


async def test_logical_projection_budget_and_alias_memoization(database, user, senses, config):
    _, sessions, _ = database
    deck = await make_node(sessions, user, config, type="DECK", name="shared", sense_ids=senses)
    alias = await make_node(
        sessions, user, config, type="REFERENCE", name="alias", reference_id=deck["id"]
    )
    await make_node(sessions, user, config, type="DECK", name="extra", sense_ids=[1])
    async with sessions() as session:
        system = await roots(session, user.id)
        root = system[NodeRole.PERSONAL_ROOT].id
    limited = config.model_copy(
        update={"projections": config.projections.model_copy(update={"max_summary_memberships": 3})}
    )
    async with sessions() as session:
        result = await summaries(session, user.id, limited, [deck["id"], alias["id"]])
        assert [r["total"] for r in result] == [2, 2]  # identical scopes charged once
        with pytest.raises(Problem, match="scope_too_large"):
            await summaries(
                session, user.id, limited, [deck["id"], root]
            )  # 2 + 3 despite 3 physical memberships


async def test_lower_hydration_bound_fails_not_partial(resources, user, senses, config):
    limited = config.model_copy(
        update={
            "projections": config.projections.model_copy(
                update={"max_word_senses": 1, "max_context_senses": 1}
            )
        }
    )
    async with client_for(resources, limited, user) as client:
        result = await client.post("/v1/words/previews", json={"word_ids": [1]})
        assert result.status_code == 422 and result.json()["error"] == "lexical_batch_too_large"
        assert (await client.get("/v1/me/words/1")).status_code == 422
