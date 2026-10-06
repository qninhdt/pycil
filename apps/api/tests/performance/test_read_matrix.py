"""Opt-in isolated EXPLAIN/load evidence. Never points at an application store."""

import asyncio
import json
import os
import platform
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from lexi_ai import Lexicon, QuestionType
from sqlalchemy import delete, event, text, update

from pycil.account.models import User
from pycil.dependencies import process_resources
from pycil.library.access import readable
from pycil.library.models import NodeRole
from pycil.library.nodes import create_node, list_nodes
from pycil.library.schemas import NodeCreate
from pycil.library.search import search_nodes
from pycil.library.senses import sense_page, sources_page
from pycil.library.tree import provision_library, roots
from pycil.study.models import UserSense
from pycil.study.preparation import prepare
from pycil.study.progress import activity, progress, schedule, summaries
from pycil.study.reviews import request_hash, review
from pycil.study.schemas import ReviewBatch
from pycil.vocabulary.context import viewer_context, word_previews

pytestmark = pytest.mark.skipif(
    os.getenv("PERF_TIER") is None, reason="Opt-in disposable performance matrix"
)
TIERS = {
    "small": (10, 500, 1000),
    "medium": (1000, 10000, 100000),
    "large": (100000, 1000000, 10000000),
}


def percentile(samples, fraction):
    return sorted(samples)[min(len(samples) - 1, int((len(samples) - 1) * fraction))]


class FixtureCompletion:
    """Deterministic provider boundary; native question validation/storage stay real."""

    async def complete(self, instruction, data, schema):
        context = json.loads(
            data.removeprefix("<question_context>").removesuffix("</question_context>").strip()
        )
        return {
            "questions": [
                {
                    "content": context["definition"],
                    "correct_explanation": "Stored meaning",
                    "distractors": [
                        {"content": word, "explanation": "Different meaning"}
                        for word in ("tree", "meal", "car")
                    ],
                }
                for _ in range(context["count"])
            ]
        }


async def test_read_matrix(database, user, deployment, reference, config, no_inference):
    tier = os.environ["PERF_TIER"]
    if tier not in TIERS:
        pytest.fail("PERF_TIER must be small, medium or large")
    if tier == "large" and os.getenv("PERF_LARGE_APPROVED") != "1":
        pytest.fail("Large tier requires explicit PERF_LARGE_APPROVED=1 resource approval")
    user_count, node_count, state_count = TIERS[tier]
    engine, sessions, _ = database
    async with engine.begin() as connection:
        await connection.execute(
            text("""INSERT INTO lexi.words(id,lemma,match_key,entry_type,generation_state)
            SELECT n,'word-'||n,'word-'||n,'WORD','DONE' FROM generate_series(1,1000) n""")
        )
        await connection.execute(
            text("""INSERT INTO lexi.senses(id,word_id,pos,tier)
            SELECT n,n,'NOUN','CORE' FROM generate_series(1,1000) n""")
        )
        await connection.execute(
            text("""INSERT INTO lexi.definitions(sense_id,content)
            SELECT n,'meaning-'||n FROM generate_series(1,1000) n""")
        )
        await connection.execute(
            text("""INSERT INTO users(id,clerk_subject,plan,settings,cycle_anchor,created_at)
            SELECT md5('perf-user-'||n)::uuid,'perf-user-'||n,'FREE','{}',now(),now()
            FROM generate_series(1,:users) n"""),
            {"users": user_count},
        )
        # Background tenants have a correct tree and sparse, explicitly described memberships.
        await connection.execute(
            text("""INSERT INTO nodes(id,owner_id,type,parent_id,name,role,space,
            created_at,updated_at)
            SELECT md5('perf-node-'||n)::uuid,md5('perf-user-'||((n-1)/:per_user+1))::uuid,
                CASE WHEN (n-1)%:per_user < 3 THEN 'FOLDER' ELSE 'DECK' END,
                CASE WHEN (n-1)%:per_user=0 THEN NULL
                     WHEN (n-1)%:per_user IN (1,2)
                     THEN md5('perf-node-'||((n-1)/:per_user*:per_user+1))::uuid
                     ELSE md5('perf-node-'||((n-1)/:per_user*:per_user+3))::uuid END,
                'catalog-'||n, CASE (n-1)%:per_user WHEN 0 THEN 'LIBRARY_ROOT'
                WHEN 1 THEN 'PERSONAL_ROOT' WHEN 2 THEN 'PUBLISHED_ROOT' ELSE 'NORMAL' END,
                CASE (n-1)%:per_user WHEN 0 THEN 'LIBRARY'
                WHEN 1 THEN 'PERSONAL' ELSE 'PUBLISHED' END,now(),now()
            FROM generate_series(1,:nodes) n"""),
            {"per_user": node_count // user_count, "nodes": node_count},
        )
        await connection.execute(
            text("""INSERT INTO node_paths(ancestor_id,descendant_id,depth)
            SELECT id,id,0 FROM nodes WHERE name LIKE 'catalog-%'
            UNION ALL SELECT parent_id,id,1 FROM nodes
            WHERE name LIKE 'catalog-%' AND parent_id IS NOT NULL
            UNION ALL SELECT r.id,d.id,2 FROM nodes d JOIN nodes p ON p.id=d.parent_id
            JOIN nodes r ON r.id=p.parent_id WHERE d.name LIKE 'catalog-%'""")
        )
        await connection.execute(
            text("""INSERT INTO deck_senses(deck_id,sense_id)
            SELECT id,1 FROM nodes WHERE type='DECK' AND name LIKE 'catalog-%'""")
        )
        await connection.execute(
            text("""INSERT INTO user_senses(user_id,sense_id,stability,difficulty,
            last_review_at,due_at,last_rating,review_count,lapse_count,created_at,updated_at)
            SELECT md5('perf-user-'||u)::uuid,s,10,5,now()-interval '1 day',
            now()+interval '1 day','GOOD',1,0,now(),now()
            FROM generate_series(1,:users) u CROSS JOIN generate_series(1,:per_user) s"""),
            {"users": user_count, "per_user": state_count // user_count},
        )
        hashes = [
            request_hash(ReviewBatch(results=[{"sense_id": i, "rating": "GOOD"}]))
            for i in range(1, state_count // user_count + 1)
        ]
        await connection.execute(
            text("""INSERT INTO review_log
            (user_id,event_key,request_hash,accepted_at,activity_day,result)
            SELECT md5('perf-user-'||u)::uuid,md5('perf-receipt-'||u||'-'||s)::uuid,
                h.hash,now(),CURRENT_DATE,jsonb_build_object(
                    'accepted_at',now(),'activity_day',CURRENT_DATE,'results',jsonb_build_array(
                        jsonb_build_object('sense_id',s,'rating','GOOD','applied',true,
                            'accepted_at',now(),'due_after',now()+interval '1 day')))
            FROM generate_series(1,:users) u
            CROSS JOIN unnest(CAST(:hashes AS text[])) WITH ORDINALITY AS h(hash,s)"""),
            {"users": user_count, "hashes": hashes},
        )
        await connection.execute(
            text("""INSERT INTO user_daily_activity
            (user_id,day,applied_events,practice_events)
            SELECT user_id,activity_day,count(*),0 FROM review_log
            GROUP BY user_id,activity_day""")
        )
    async with sessions() as session:
        system = await roots(session, user.id)
        library = system[NodeRole.LIBRARY_ROOT].id
        personal = system[NodeRole.PERSONAL_ROOT].id
        published = system[NodeRole.PUBLISHED_ROOT].id
    cards = []
    for i in range(50):
        async with sessions() as session:
            cards.append(
                await create_node(
                    session,
                    user.id,
                    NodeCreate(
                        type="DECK",
                        name=f"hot bank-{i}",
                        parent_id=published,
                        confirm_publication=True,
                        sense_ids=list(range(1, 1001)),
                    ),
                    config,
                )
            )
    async with sessions() as session:
        empty = await create_node(
            session, user.id, NodeCreate(type="DECK", name="empty", parent_id=personal), config
        )

    # Exact 100k owned memberships plus 100k remote memberships; public cycles
    # and repeated aliases make the Library scope reach the physical work bound.
    async def add_node(owner, **values):
        async with sessions() as session:
            return await create_node(session, owner, NodeCreate(**values), config)

    for i in range(50):
        await add_node(
            user.id,
            type="DECK",
            name=f"personal-{i}",
            parent_id=personal,
            sense_ids=list(range(1, 1001)),
        )
    remote_folders, remote_owners = [], []
    for index in range(2):
        remote = User(clerk_subject="hot-remote-" + uuid4().hex, settings={})
        async with sessions() as session, session.begin():
            session.add(remote)
            await session.flush()
            await provision_library(session, remote.id)
            public_root = (await roots(session, remote.id))[NodeRole.PUBLISHED_ROOT].id
        folder = await add_node(
            remote.id,
            type="FOLDER",
            name=f"remote-{index}",
            parent_id=public_root,
            confirm_publication=True,
        )
        remote_folders.append(folder)
        remote_owners.append(remote.id)
        for i in range(50):
            await add_node(
                remote.id,
                type="DECK",
                name=f"remote-bank-{index}-{i}",
                parent_id=folder["id"],
                confirm_publication=True,
                sense_ids=list(range(1, 1001)),
            )
    for index in range(2):
        await add_node(
            remote_owners[index],
            type="REFERENCE",
            name="cycle",
            parent_id=remote_folders[index]["id"],
            confirm_publication=True,
            reference_id=remote_folders[1 - index]["id"],
        )
    aliases = []
    for i in range(10):
        aliases.append(
            await add_node(
                user.id,
                type="REFERENCE",
                name=f"alias-{i}",
                parent_id=personal,
                reference_id=remote_folders[i % 2]["id"],
            )
        )
    generator = Lexicon(
        db_url=deployment.db_url.get_secret_value(),
        db_schema="lexi",
        cambridge_path=str(reference),
        llm=FixtureCompletion(),
    )
    try:
        for sense_id in range(1, 31):
            await generator.generate_questions(
                sense_id, QuestionType.DEFINITION_TO_WORD, 3, distractor_count=3
            )
    finally:
        await generator.close()
    async with engine.begin() as connection:
        await connection.execute(text("ANALYZE"))
        settings = dict(
            (
                await connection.execute(
                    text(
                        "SELECT name,setting FROM pg_settings WHERE name IN "
                        "('shared_buffers','work_mem','max_connections','server_version')"
                    )
                )
            ).all()
        )
    captured = []
    query_ms = []
    lock_samples = []
    report = {
        "tier": tier,
        "background_users": user_count,
        "background_nodes": node_count,
        "background_states": state_count,
        "background_receipts": state_count,
        "hot_owner_decks": 50,
        "hot_owner_memberships": 50000,
        "hot_owner_private_memberships": 50000,
        "hot_remote_memberships": 100000,
        "near_budget_scope_memberships": 200000,
        "repeated_aliases": 10,
        "cyclic_remote_owners": 2,
        "ready_senses": 30,
        "background_memberships": "one per deck",
        "hardware": {"platform": platform.platform(), "logical_cpus": os.cpu_count()},
        "postgresql": settings,
        "api_processes": 1,
        "concurrency": 4,
        "provider_calls": 0,
        "cold_note": "first native read only; not OS-cold PostgreSQL",
        "workloads": {},
        "plans": {},
        "sla": "No approved deployment thresholds; not a capacity certification",
    }

    def capture(_conn, _cursor, statement, parameters, *_):
        _conn.info["perf_query_start"] = perf_counter()
        if "pg_advisory_xact_lock" in statement:
            _conn.info["perf_lock_start"] = perf_counter()
        if (
            statement.lstrip().startswith(("SELECT", "WITH"))
            and "set_config" not in statement
            and "advisory" not in statement
        ):
            captured.append((statement, parameters, _conn.engine is not engine.sync_engine))

    def completed(conn, _cursor, statement, *_):
        started_query = conn.info.pop("perf_query_start", None)
        if started_query is not None:
            query_ms.append((perf_counter() - started_query) * 1000)
        started = conn.info.pop("perf_lock_start", None)
        if started is not None:
            lock_samples.append((perf_counter() - started) * 1000)

    async with process_resources(config, deployment) as resources:
        event.listen(engine.sync_engine, "before_cursor_execute", capture)
        event.listen(engine.sync_engine, "after_cursor_execute", completed)
        event.listen(resources.lexicon.db.engine.sync_engine, "before_cursor_execute", capture)
        try:

            async def run(kind):
                async with sessions() as session:
                    if kind == "cards_5":
                        return await summaries(
                            session, user.id, config, [n["id"] for n in cards[:5]]
                        )
                    if kind == "cards_50":
                        return await summaries(session, user.id, config, [n["id"] for n in cards])
                    if kind == "children":
                        return await list_nodes(session, user.id, published, None, config)
                    if kind == "inline_cards":
                        return await list_nodes(
                            session, user.id, published, None, config, include="summary"
                        )
                    if kind == "summary_empty":
                        return await progress(session, user, config, empty["id"])
                    if kind == "summary_large":
                        return await progress(session, user, config, published)
                    if kind == "summary_near_budget":
                        return await progress(session, user, config)
                    if kind == "alias_cards":
                        return await summaries(session, user.id, config, [n["id"] for n in aliases])
                    if kind == "reference_cycle":
                        return await progress(session, user, config, remote_folders[0]["id"])
                    if kind == "context":
                        return await viewer_context(session, user.id, config, list(range(1, 101)))
                    if kind == "previews":
                        return await word_previews(
                            session, resources.lexicon, list(range(1, 31)), config
                        )
                    if kind == "source_overflow":
                        return await sources_page(session, published, 1, user.id, config, limit=5)
                    if kind == "scope_search":
                        return await search_nodes(
                            session, user.id, config, node_id=published, q="bank"
                        )
                    if kind == "library_search":
                        return await search_nodes(
                            session, user.id, config, node_id=library, q="bank"
                        )
                    if kind == "catalog_browse":
                        return await search_nodes(session, None, config)
                    if kind == "catalog_broad":
                        return await search_nodes(session, None, config, q="catalog")
                    if kind == "catalog_owner":
                        return await search_nodes(session, None, config, owner_id=user.id)
                    if kind == "catalog_type":
                        from pycil.library.models import NodeType

                        return await search_nodes(session, None, config, type=NodeType.DECK)
                    if kind == "lexical_search":
                        return await resources.lexicon.search("word", include_available=True)
                    if kind == "lexical_refresh":
                        fresh = Lexicon(
                            db_url=deployment.db_url.get_secret_value(),
                            db_schema="lexi",
                            cambridge_path=str(reference),
                            llm=FixtureCompletion(),
                        )
                        event.listen(fresh.db.engine.sync_engine, "before_cursor_execute", capture)
                        try:
                            await fresh.start()
                            return await fresh.search("word", include_available=True)
                        finally:
                            event.remove(
                                fresh.db.engine.sync_engine, "before_cursor_execute", capture
                            )
                            await fresh.close()
                    if kind == "activity":
                        return await activity(session, user.id, config)
                    if kind == "schedule":
                        return await schedule(session, user.id, config)
                    if kind == "receipt_replay":
                        return await review(session, user.id, batch, key, config)
                    if kind == "overlapping_writes":
                        return await review(
                            session,
                            user.id,
                            ReviewBatch(
                                results=[{"sense_id": i, "rating": "AGAIN"} for i in (1, 2)]
                            ),
                            uuid4(),
                            config,
                        )
                    if kind.startswith("prepare_"):
                        return await prepare(
                            session,
                            resources.lexicon,
                            user,
                            published,
                            config,
                            selection=kind[8:].removesuffix("_starved"),
                            max_sense_count=30 if kind.endswith("_starved") else 10,
                        )
                    node = await readable(session, published, user.id, config)
                    return await sense_page(
                        session,
                        node,
                        user.id,
                        config,
                        resources.lexicon,
                        q="no-match" if kind == "senses_no_match" else None,
                        sort="LEMMA_ASC"
                        if kind == "senses_lemma"
                        else "LAST_REVIEWED_DESC"
                        if kind == "senses_reviewed"
                        else "SENSE_ID_ASC",
                        include="sources,examples",
                    )

            batch = ReviewBatch(results=[{"sense_id": i, "rating": "GOOD"} for i in range(1, 101)])
            key = uuid4()
            async with sessions() as session:
                await review(session, user.id, batch, key, config)
            async with sessions() as session, session.begin():
                await session.execute(
                    update(UserSense)
                    .where(
                        UserSense.user_id == user.id,
                        UserSense.sense_id <= 10,
                    )
                    .values(due_at=datetime.now(UTC) - timedelta(days=1))
                )
                await session.execute(
                    delete(UserSense).where(
                        UserSense.user_id == user.id,
                        UserSense.sense_id.between(11, 20),
                    )
                )
            for kind in (
                "cards_5",
                "cards_50",
                "children",
                "inline_cards",
                "summary_empty",
                "summary_large",
                "summary_near_budget",
                "alias_cards",
                "reference_cycle",
                "context",
                "previews",
                "source_overflow",
                "scope_search",
                "library_search",
                "catalog_browse",
                "catalog_broad",
                "catalog_owner",
                "catalog_type",
                "lexical_search",
                "lexical_refresh",
                "activity",
                "schedule",
                "receipt_replay",
                "prepare_NEW",
                "prepare_DUE",
                "prepare_AUTO",
                "prepare_AUTO_starved",
                "senses_no_match",
                "senses_lemma",
                "senses_reviewed",
                "overlapping_writes",
            ):
                captured.clear()
                query_ms.clear()
                lock_samples.clear()
                start = perf_counter()
                first_result = await run(kind)
                if kind in {"prepare_AUTO", "prepare_DUE", "prepare_NEW"}:
                    assert first_result["actual_sense_count"] == 10
                    assert first_result["actual_question_count"] == 30
                    if kind == "prepare_AUTO":
                        assert {b["reason"] for b in first_result["bundles"]} == {"DUE"}
                if kind == "summary_near_budget":
                    assert first_result["total"] == 1000
                first_ms = (perf_counter() - start) * 1000
                first_queries = list(captured)
                first_query_ms = list(query_ms)
                if kind in {"scope_search", "library_search"}:
                    assert all("deck_senses" not in sql for sql, _, _ in first_queries)
                samples = []
                request_samples = []

                async def timed_run(kind=kind, request_samples=request_samples):
                    started = perf_counter()
                    result = await run(kind)
                    request_samples.append((perf_counter() - started) * 1000)
                    return result

                for _ in range(5):
                    start = perf_counter()
                    await asyncio.gather(*(timed_run() for _ in range(4)))
                    samples.append((perf_counter() - start) * 1000)
                report["workloads"][kind] = {
                    "first_ms": first_ms,
                    "first_queries": len(first_queries),
                    "first_query_ms": first_query_ms,
                    "samples": 5,
                    "concurrent_requests_per_sample": 4,
                    "group_p50_ms": percentile(samples, 0.5),
                    "group_p95_ms": percentile(samples, 0.95),
                    "group_p99_ms": percentile(samples, 0.99),
                    "request_p50_ms": percentile(request_samples, 0.5),
                    "request_p95_ms": percentile(request_samples, 0.95),
                    "request_p99_ms": percentile(request_samples, 0.99),
                    "throughput_rps": 20 / (sum(samples) / 1000),
                    "errors": 0,
                    "advisory_lock_calls": len(lock_samples),
                    "advisory_roundtrip_p95_ms": percentile(lock_samples, 0.95)
                    if lock_samples
                    else None,
                    "advisory_roundtrip_max_ms": max(lock_samples) if lock_samples else None,
                }
                plans = []
                for statement, parameters, native in first_queries:
                    async with engine.connect() as connection:
                        await connection.execute(
                            text(
                                "SET LOCAL search_path = lexi, public"
                                if native
                                else "SET LOCAL search_path = public"
                            )
                        )
                        value = await connection.exec_driver_sql(
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
                        )
                        plans.append(
                            {
                                "sql": statement,
                                "schema": "lexi" if native else "public",
                                "plan": value.scalar(),
                            }
                        )
                report["plans"][kind] = plans
            assert (
                report["workloads"]["cards_5"]["first_queries"]
                == report["workloads"]["cards_50"]["first_queries"]
            )
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", capture)
            event.remove(engine.sync_engine, "after_cursor_execute", completed)
            event.remove(resources.lexicon.db.engine.sync_engine, "before_cursor_execute", capture)
            output = Path(os.getenv("PERF_OUTPUT", "/tmp/opencode/pycil-performance"))
            output.mkdir(parents=True, exist_ok=True)
            (output / (tier + "-" + uuid4().hex + ".json")).write_text(
                json.dumps(report, indent=2, default=str)
            )
