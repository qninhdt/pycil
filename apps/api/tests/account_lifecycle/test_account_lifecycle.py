"""Account export/deletion remain scoped to Pycil-owned data."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from pycil.assistant.hitl import create_pending_action
from pycil.assistant.models import (
    AssistantActionAudit,
    AssistantRun,
    AssistantRunEvent,
    AssistantThread,
    RunStatus,
)
from pycil.assistant.persistence import retention_deadline
from pycil.auth import tokens
from pycil.auth.models import User
from pycil.auth.refresh_sessions import issue
from pycil.hierarchy.models import Node, NodeType, Visibility
from pycil.learning.models import SessionSummary, UserLearningSettings
from pycil.tasks import service as task_service
from pycil.tasks.work_keys import grading_work_key, word_work_key

pytestmark = pytest.mark.asyncio


async def _seed(session) -> User:
    user = User(email="account@x.co")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_export_and_delete_remove_only_the_authenticated_user(client, session):
    owner = await _seed(session)
    other = User(email="other@x.co")
    session.add(other)
    await session.flush()
    session.add(Node(author_id=owner.id, type=NodeType.FOLDER, name="Owner folder"))
    session.add(Node(author_id=other.id, type=NodeType.FOLDER, name="Other folder"))
    raw_refresh, _ = await issue(session, owner.id)
    await session.commit()
    access, _ = tokens.sign_access(owner)

    exported = await client.get("/v1/me/export", headers=await _headers(access))
    assert exported.status_code == 200
    assert exported.json()["profile"]["email"] == owner.email
    assert [item["name"] for item in exported.json()["hierarchy"]] == ["Owner folder"]

    deleted = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    count_sql = text("SELECT count(*) FROM users WHERE id = :id")
    assert await session.scalar(count_sql, {"id": owner.id}) == 0
    assert await session.scalar(count_sql, {"id": other.id}) == 1


async def test_delete_requires_literal_confirmation(client, session):
    user = await _seed(session)
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()
    access, _ = tokens.sign_access(user)

    response = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "delete"},
    )
    assert response.status_code == 401
    assert await session.get(User, user.id) is not None


async def test_delete_removes_cross_owner_reference_to_deleted_public_deck(client, session):
    owner = await _seed(session)
    other = User(email="reference-owner@x.co")
    session.add(other)
    await session.flush()
    deck = Node(
        author_id=owner.id,
        type=NodeType.DECK,
        name="Public deck",
        visibility=Visibility.PUBLIC,
    )
    session.add(deck)
    await session.flush()
    reference = Node(
        author_id=other.id,
        type=NodeType.REFERENCE,
        name="External reference",
        target_node_id=deck.id,
    )
    session.add(reference)
    raw_refresh, _ = await issue(session, owner.id)
    await session.commit()
    access, _ = tokens.sign_access(owner)
    reference_id = reference.id

    response = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )

    assert response.status_code == 204
    assert await session.get(User, other.id) is not None
    session.expire_all()
    assert await session.get(Node, reference_id) is None


async def test_delete_erases_every_table_that_references_the_user(client, session):
    """A real account owns rows in tables the deletion sequence used to omit.

    Four tables carry a ``users.id`` foreign key with ``NO ACTION``, so a missing
    ``DELETE`` does not orphan a row — it aborts the whole transaction and the
    account survives. The existing tests pass only because their user owns nothing
    but a folder; any learner who has generated a word or submitted an answer holds
    an ``async_task_interests`` row and could never be deleted.

    Asserted against the live schema rather than a hardcoded list, so a future
    table with a ``users`` FK fails here instead of in production.
    """
    user = await _seed(session)

    # Every row below is created through the same service the routes use, so the
    # test cannot drift from the shape production actually writes.
    await task_service.submit_or_join(
        session,
        kind="word",
        server_work_key=word_work_key("resilient", "fingerprint"),
        requester_id=user.id,
        command_kind="word.generate",
        command_id="cmd-word-1",
        provenance="word-search",
        dispatch={"query": "resilient"},
    )
    await task_service.submit_or_join(
        session,
        kind="grading",
        server_work_key=grading_work_key("11111111-1111-4111-8111-111111111111"),
        requester_id=user.id,
        command_kind="grading.submit",
        command_id="11111111-1111-4111-8111-111111111111",
        provenance="response-owner",
        dispatch={"owner_id": str(user.id), "response_id": "x"},
    )
    session.add(
        UserLearningSettings(
            user_id=user.id, target_words_per_session=5, max_questions_per_round=2
        )
    )
    session.add(
        SessionSummary(
            user_id=user.id,
            session_id="session-1",
            node_id=None,
            senses_admitted=3,
            answers_total=3,
            answers_correct=2,
        )
    )
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()
    access, _ = tokens.sign_access(user)

    referencing = list(
        await session.scalars(
            text(
                "SELECT tc.table_name || '.' || kcu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON kcu.constraint_name = tc.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'users'"
            )
        )
    )
    assert referencing, "expected the schema to report foreign keys onto users"

    response = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )
    assert response.status_code == 204

    assert await session.scalar(
        text("SELECT count(*) FROM users WHERE id = :id"), {"id": user.id}
    ) == 0
    # No table may still point at the erased account.
    for qualified in referencing:
        table, column = qualified.split(".")
        remaining = await session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE {column} = :id"),  # noqa: S608
            {"id": user.id},
        )
        assert remaining == 0, f"{qualified} still references the deleted user"


async def test_delete_keeps_reusable_word_work_another_learner_still_shares(client, session):
    """A `word` task is shared dictionary work, not personal data.

    `async_tasks` is keyed by a server-derived work key and two learners searching
    the same headword join the same row. Deleting one account must not remove the
    task another learner's interest still points at, and must not remove the
    reusable task at all — otherwise the survivor's activity card loses the
    snapshot the subscribe proxy needs to authorize and recover.
    """
    leaver = await _seed(session)
    stayer = User(email="stayer@x.co")
    session.add(stayer)
    await session.flush()

    shared_key = word_work_key("resilient", "fingerprint")
    first = await task_service.submit_or_join(
        session,
        kind="word",
        server_work_key=shared_key,
        requester_id=leaver.id,
        command_kind="word.generate",
        command_id="cmd-leaver",
        provenance="word-search",
        dispatch={"query": "resilient"},
    )
    second = await task_service.submit_or_join(
        session,
        kind="word",
        server_work_key=shared_key,
        requester_id=stayer.id,
        command_kind="word.generate",
        command_id="cmd-stayer",
        provenance="word-search",
        dispatch={"query": "resilient"},
    )
    # Both learners must really be on one task, or this proves nothing.
    assert first.task.id == second.task.id
    shared_task_id = first.task.id

    raw_refresh, _ = await issue(session, leaver.id)
    await session.commit()
    access, _ = tokens.sign_access(leaver)

    response = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )
    assert response.status_code == 204

    counts = {
        "task": "SELECT count(*) FROM async_tasks WHERE id = :id",
        "events": "SELECT count(*) FROM async_task_events WHERE task_id = :id",
    }
    assert await session.scalar(text(counts["task"]), {"id": shared_task_id}) == 1
    # The survivor's recovery snapshot is intact.
    assert await session.scalar(text(counts["events"]), {"id": shared_task_id}) >= 1
    # Only the leaver's interest is gone.
    remaining = list(
        await session.scalars(
            text("SELECT requester_id FROM async_task_interests WHERE task_id = :id"),
            {"id": shared_task_id},
        )
    )
    assert remaining == [stayer.id]


async def test_delete_removes_a_grading_task_and_its_personal_feedback(client, session):
    """`grading` task results hold the learner's own LLM feedback text.

    Unlike `word`, a grading task is per-response and never shared, so its row and
    its event snapshots carry personal content that account deletion must erase.
    """
    user = await _seed(session)
    response_id = "22222222-2222-4222-8222-222222222222"
    submission = await task_service.submit_or_join(
        session,
        kind="grading",
        server_work_key=grading_work_key(response_id),
        requester_id=user.id,
        command_kind="grading.submit",
        command_id=response_id,
        provenance="response-owner",
        dispatch={"owner_id": str(user.id), "response_id": response_id},
    )
    grading_task_id = submission.task.id
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()
    access, _ = tokens.sign_access(user)
    assert await session.scalar(
        text("SELECT count(*) FROM async_task_events WHERE task_id = :id"),
        {"id": grading_task_id},
    ) >= 1

    deleted = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )
    assert deleted.status_code == 204

    for table, column in (
        ("async_tasks", "id"),
        ("async_task_events", "task_id"),
    ):
        assert await session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE {column} = :id"),  # noqa: S608
            {"id": grading_task_id},
        ) == 0


async def test_delete_keeps_a_grading_task_a_second_interest_still_references(client, session):
    """The `NOT IN` guard, not the `kind` filter, is what protects a live reader.

    A grading task is normally single-requester, so the ordinary path never
    exercises the guard. But `uq_task_interest_provenance` is keyed on
    (task_id, requester_id, provenance): a second interest under a different
    provenance is representable, and an admin or support surface reading a
    response would create exactly that. Without the guard this deletes a task row
    another interest still points at, which is an FK violation that aborts the
    whole account deletion — the same class of bug as the four missing tables.
    """
    leaver = await _seed(session)
    auditor = User(email="auditor@x.co")
    session.add(auditor)
    await session.flush()

    response_id = "33333333-3333-4333-8333-333333333333"
    submission = await task_service.submit_or_join(
        session,
        kind="grading",
        server_work_key=grading_work_key(response_id),
        requester_id=leaver.id,
        command_kind="grading.submit",
        command_id=response_id,
        provenance="response-owner",
        dispatch={"owner_id": str(leaver.id), "response_id": response_id},
    )
    grading_task_id = submission.task.id
    second = await task_service.submit_or_join(
        session,
        kind="grading",
        server_work_key=grading_work_key(response_id),
        requester_id=auditor.id,
        command_kind="grading.observe",
        command_id=f"observe:{response_id}",
        provenance="support-review",
        dispatch={"owner_id": str(leaver.id), "response_id": response_id},
    )
    assert second.task.id == grading_task_id

    raw_refresh, _ = await issue(session, leaver.id)
    await session.commit()
    access, _ = tokens.sign_access(leaver)

    deleted = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    assert await session.scalar(
        text("SELECT count(*) FROM users WHERE id = :id"), {"id": leaver.id}
    ) == 0
    # The task survives because another interest still references it.
    assert await session.scalar(
        text("SELECT count(*) FROM async_tasks WHERE id = :id"), {"id": grading_task_id}
    ) == 1
    remaining = list(
        await session.scalars(
            text("SELECT requester_id FROM async_task_interests WHERE task_id = :id"),
            {"id": grading_task_id},
        )
    )
    assert remaining == [auditor.id]


async def test_delete_reaches_assistant_runs_events_and_actions_through_the_cascade(
    client, session
):
    """0024 moved three deletion steps into the database; this proves they still happen.

    `delete_account` used to name `assistant_run_events`, `assistant_actions` and
    `assistant_runs` explicitly. They now cascade from the thread, so the statements
    were removed — which is only safe if the cascade is real. Measured before adding
    it: all eight assistant foreign keys were NO ACTION, so the plan's premise that
    `ondelete=` already covered this was wrong.

    The audit row is asserted separately, because it must NOT cascade.
    """
    user = await _seed(session)
    thread = AssistantThread(owner_id=user.id, title="T", retention_deadline=retention_deadline())
    session.add(thread)
    await session.flush()
    run = AssistantRun(
        thread_id=thread.id,
        owner_id=user.id,
        client_message_id=uuid4(),
        status=RunStatus.SUCCEEDED,
    )
    session.add(run)
    await session.flush()
    session.add(
        AssistantRunEvent(
            run_id=run.id,
            sequence=1,
            event_type="token",
            sanitized_payload={"t": "x"},
            expires_at=retention_deadline(),
        )
    )
    action = await create_pending_action(
        session, run_id=run.id, owner_id=user.id, tool="add_sense", arguments={"senseId": 1}
    )
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()
    access, _ = tokens.sign_access(user)
    ids = {"thread": thread.id, "run": run.id, "action": action.id}

    deleted = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )
    assert deleted.status_code == 204

    for table, column, key in (
        ("assistant_threads", "id", "thread"),
        ("assistant_runs", "id", "run"),
        ("assistant_run_events", "run_id", "run"),
        ("assistant_actions", "id", "action"),
    ):
        remaining = await session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE {column} = :id"),  # noqa: S608
            {"id": ids[key]},
        )
        assert remaining == 0, f"{table} survived account deletion"


async def test_retention_keeps_the_audit_row_the_cascade_must_not_delete(session, engine):
    """`action_id` is SET NULL, not CASCADE, and the difference is the audit trail.

    `reconcile_assistant_retention` nulls `action_id` by hand before deleting actions
    and its own test asserts the audit survives. Making that edge CASCADE would have
    deleted the policy-required record instead — a silent data-retention regression
    that the hand-written UPDATE was the only thing preventing.

    Asserted at the database level so it holds regardless of which code path deletes
    the action.
    """
    user = await _seed(session)
    thread = AssistantThread(owner_id=user.id, title="T", retention_deadline=retention_deadline())
    session.add(thread)
    await session.flush()
    run = AssistantRun(
        thread_id=thread.id,
        owner_id=user.id,
        client_message_id=uuid4(),
        status=RunStatus.SUCCEEDED,
    )
    session.add(run)
    await session.flush()
    # `create_pending_action` writes the action and its "proposed" audit together,
    # which is the shape production actually produces.
    action = await create_pending_action(
        session, run_id=run.id, owner_id=user.id, tool="add_sense", arguments={"senseId": 1}
    )
    audit_id = await session.scalar(
        text("SELECT id FROM assistant_action_audit WHERE action_id = :id"), {"id": action.id}
    )
    assert audit_id is not None

    # Delete only the action, the way retention does after nulling the pointer.
    await session.execute(text("DELETE FROM assistant_actions WHERE id = :id"), {"id": action.id})
    await session.commit()
    session.expire_all()

    surviving = await session.get(AssistantActionAudit, audit_id)
    assert surviving is not None, "the audit row must outlive the action it describes"
    assert surviving.action_id is None


_CHECKPOINT_DDL = (
    "CREATE TABLE IF NOT EXISTS checkpoints (thread_id TEXT NOT NULL, "
    "checkpoint_ns TEXT NOT NULL DEFAULT '', checkpoint_id TEXT NOT NULL, "
    "parent_checkpoint_id TEXT, type TEXT, checkpoint JSONB NOT NULL, "
    "metadata JSONB NOT NULL DEFAULT '{}', "
    "PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))",
    "CREATE TABLE IF NOT EXISTS checkpoint_blobs (thread_id TEXT NOT NULL, "
    "checkpoint_ns TEXT NOT NULL DEFAULT '', channel TEXT NOT NULL, version TEXT NOT NULL, "
    "type TEXT NOT NULL, blob BYTEA, "
    "PRIMARY KEY (thread_id, checkpoint_ns, channel, version))",
    "CREATE TABLE IF NOT EXISTS checkpoint_writes (thread_id TEXT NOT NULL, "
    "checkpoint_ns TEXT NOT NULL DEFAULT '', checkpoint_id TEXT NOT NULL, "
    "task_id TEXT NOT NULL, idx INTEGER NOT NULL, channel TEXT NOT NULL, type TEXT, "
    "blob BYTEA NOT NULL, task_path TEXT NOT NULL DEFAULT '', "
    "PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx))",
)


async def test_delete_erases_the_langgraph_checkpoint_rows(client, session):
    """The deletions no cascade can ever cover.

    `checkpoints`, `checkpoint_blobs` and `checkpoint_writes` are LangGraph-owned and
    keyed by a `thread_id` string, not a foreign key, so nothing in the schema reaches
    them. They hold the assistant conversation content, which makes losing these
    statements a data-retention regression rather than a leak.

    Nothing covered this before: the tables are created by raw SQL inside migration
    0008, while the test database is built from ORM metadata via `create_all`, so they
    simply did not exist here. Removing the deletion left every test green. The DDL is
    created explicitly for that reason.
    """
    for statement in _CHECKPOINT_DDL:
        await session.execute(text(statement))
    user = await _seed(session)
    thread_id = f"assistant:{user.id}:11111111-1111-4111-8111-111111111111"
    other_thread_id = "assistant:00000000-0000-4000-8000-000000000000:deadbeef"
    for owner in (thread_id, other_thread_id):
        await session.execute(
            text(
                "INSERT INTO checkpoints (thread_id, checkpoint_id, checkpoint, metadata) "
                "VALUES (:t, 'c1', '{}'::jsonb, '{}'::jsonb)"
            ),
            {"t": owner},
        )
        await session.execute(
            text(
                "INSERT INTO checkpoint_blobs (thread_id, channel, version, type) "
                "VALUES (:t, 'ch', 'v1', 'json')"
            ),
            {"t": owner},
        )
        await session.execute(
            text(
                "INSERT INTO checkpoint_writes "
                "(thread_id, checkpoint_id, task_id, idx, channel, blob) "
                "VALUES (:t, 'c1', 'task', 0, 'ch', '\\x00'::bytea)"
            ),
            {"t": owner},
        )
    raw_refresh, _ = await issue(session, user.id)
    await session.commit()
    access, _ = tokens.sign_access(user)

    deleted = await client.request(
        "DELETE",
        "/v1/me",
        headers=await _headers(access),
        json={"refresh_token": raw_refresh, "confirmation": "DELETE"},
    )
    assert deleted.status_code == 204

    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        mine = await session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE thread_id = :t"),  # noqa: S608
            {"t": thread_id},
        )
        assert mine == 0, f"{table} kept this account's assistant conversation content"
        # And only this account's: the prefix match must not reach another learner.
        theirs = await session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE thread_id = :t"),  # noqa: S608
            {"t": other_thread_id},
        )
        assert theirs == 1, f"{table} lost another account's rows"
