"""Account invariants."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pycil.account.deletion import delete_account
from pycil.account.export import export_account
from pycil.account.user import User
from pycil.assistant.models import AssistantThread
from pycil.assistant.turns.settlement import (
    settle_assistant_segment,
)
from pycil.assistant.turns.usage import CallUsage, TurnUsage
from pycil.billing.errors import UsageQuotaExhaustedError
from pycil.billing.ledger import (
    get_or_create_account_plan,
    get_or_create_usage_period,
    get_usage_allowance,
    record_usage,
    require_usage_allowed,
    set_plan,
)
from pycil.billing.plans import FeatureKey, PlanKey, get_plan
from pycil.library.models import DeckSense, Node, NodeType, Visibility
from pycil.platform.errors import ServiceUnavailableError

pytestmark = pytest.mark.asyncio


async def _user(session, prefix: str = "account") -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_plan_shape_has_two_tiers_and_an_allowance():
    assert set(PlanKey) == {PlanKey.free, PlanKey.pro}
    assert get_plan(PlanKey.free).monthly_credit_units < get_plan(PlanKey.pro).monthly_credit_units


async def test_debit_rolls_elapsed_period_and_is_idempotent(session):
    user = await _user(session)
    now = datetime(2030, 1, 31, tzinfo=UTC)
    anchor = now - timedelta(days=31)
    plan = await get_or_create_account_plan(session, user_id=user.id, moment=anchor)
    old_period = await get_or_create_usage_period(
        session, user_id=user.id, moment=anchor, plan=plan
    )
    old_period.used_units = old_period.allowance_units
    await session.commit()
    reference = uuid4()

    period = await get_or_create_usage_period(session, user_id=user.id, moment=now)
    first = await record_usage(
        session,
        user_id=user.id,
        period_id=period.id,
        event_key=f"level4_grading:{reference}",
        feature_key=FeatureKey.LEVEL4_GRADING,
        units=10,
        occurred_at=now,
    )
    await session.commit()
    second = await record_usage(
        session,
        user_id=user.id,
        period_id=period.id,
        event_key=f"level4_grading:{reference}",
        feature_key=FeatureKey.LEVEL4_GRADING,
        units=10,
        occurred_at=now,
    )
    await session.commit()

    current = await get_usage_allowance(session, user.id, moment=now)
    assert first.event_id == second.event_id
    assert second.idempotent_replay is True
    assert current.used_units == 10
    assert current.raw_remaining_units == get_plan(PlanKey.free).monthly_credit_units - 10
    assert (
        await session.scalar(
            text(
                "SELECT count(*) FROM usage_events e "
                "JOIN usage_periods p ON p.id = e.period_id WHERE p.user_id = :user_id"
            ),
            {"user_id": user.id},
        )
        == 1
    )


async def test_assistant_segments_settle_independently_and_idempotently(session):
    user = await _user(session, "assistant-resume")
    run_id = str(uuid4())
    now = datetime(2030, 4, 12, tzinfo=UTC)

    # 1. Initial segment admits and interrupts
    balance_1 = await require_usage_allowed(
        session, user.id, feature=FeatureKey.ASSISTANT, moment=now
    )
    usage_1 = TurnUsage()
    usage_1.add("gemini-3.8-flash", CallUsage(input_tokens=1000, output_tokens=100))
    settlement_1 = await settle_assistant_segment(
        session,
        user_id=user.id,
        period_id=balance_1.period_id,
        occurred_at=now,
        run_id=run_id,
        status="interrupted",
        usage=usage_1,
    )
    assert settlement_1 is not None
    await session.commit()

    # 2. Resume segment admits and completes
    balance_2 = await require_usage_allowed(
        session, user.id, feature=FeatureKey.ASSISTANT, moment=now
    )
    usage_2 = TurnUsage()
    usage_2.add("gemini-3.8-flash", CallUsage(input_tokens=2000, output_tokens=200))
    settlement_2 = await settle_assistant_segment(
        session,
        user_id=user.id,
        period_id=balance_2.period_id,
        occurred_at=now,
        run_id=run_id,
        status="completed",
        usage=usage_2,
        interrupt_id="int-1",
    )
    assert settlement_2 is not None
    await session.commit()

    # 3. Replay resume segment
    replay = await settle_assistant_segment(
        session,
        user_id=user.id,
        period_id=balance_2.period_id,
        occurred_at=now,
        run_id=run_id,
        status="completed",
        usage=usage_2,
        interrupt_id="int-1",
    )
    assert replay is not None
    assert replay.idempotent_replay is True
    await session.commit()

    current = await get_usage_allowance(session, user.id, moment=now)
    assert current.used_units == settlement_1.units + settlement_2.units
    assert (
        await session.scalar(
            text(
                "SELECT count(*) FROM usage_events e "
                "JOIN usage_periods p ON p.id = e.period_id WHERE p.user_id = :user_id"
            ),
            {"user_id": user.id},
        )
        == 2
    )


async def test_submit_gate_is_typed_and_balance_is_one_pool(session):
    user = await _user(session)
    snapshot = await get_usage_allowance(session, user.id)
    assert snapshot.raw_remaining_units == get_plan(PlanKey.free).monthly_credit_units
    await require_usage_allowed(
        session, user.id, feature=FeatureKey.LEVEL4_GRADING, required_units=1
    )

    period = await get_or_create_usage_period(session, user_id=user.id)
    period.used_units = period.allowance_units
    await session.commit()
    with pytest.raises(UsageQuotaExhaustedError):
        await require_usage_allowed(
            session, user.id, feature=FeatureKey.LEVEL4_GRADING, required_units=1
        )


async def test_reads_reflect_elapsed_rollover_before_any_debit(session):
    user = await _user(session)
    now = datetime.now(UTC)
    past_anchor = now - timedelta(days=95)
    plan = await get_or_create_account_plan(session, user_id=user.id, moment=past_anchor)
    old_period = await get_or_create_usage_period(
        session, user_id=user.id, moment=past_anchor, plan=plan
    )
    old_period.used_units = old_period.allowance_units
    await session.commit()

    snapshot = await get_usage_allowance(session, user.id)
    assert snapshot.raw_remaining_units == get_plan(PlanKey.free).monthly_credit_units
    await require_usage_allowed(
        session, user.id, feature=FeatureKey.LEVEL4_GRADING, required_units=1
    )


async def test_the_allowance_is_clamped_for_display_but_stays_signed(session):
    """An admitted turn may overshoot; the UI must not show a negative allowance."""
    user = await _user(session)
    period = await get_or_create_usage_period(session, user_id=user.id)
    await record_usage(
        session,
        user_id=user.id,
        period_id=period.id,
        event_key=f"level4_grading:{uuid4()}",
        feature_key=FeatureKey.LEVEL4_GRADING,
        units=get_plan(PlanKey.free).monthly_credit_units + 250,
    )
    await session.commit()

    current = await get_usage_allowance(session, user.id)
    assert current.raw_remaining_units == -250, (
        "the ledger records the overshoot it actually incurred"
    )
    assert current.remaining_units == 0, "display clamps, the stored balance does not"
    with pytest.raises(UsageQuotaExhaustedError):
        await require_usage_allowed(
            session, user.id, feature=FeatureKey.LEVEL4_GRADING, required_units=1
        )


async def test_export_contains_plan_and_credit_but_no_dictionary_rows(session):
    user = await _user(session)
    await set_plan(session, user.id, PlanKey.pro)
    await session.commit()

    exported = await export_account(session, user.id)

    assert exported["plan"] == "pro"
    assert "credit" in exported
    assert "dictionary" not in exported
    assert "words" not in exported
    assert "senses" not in exported["learning"]


async def test_delete_is_ordered_and_keeps_nodes_and_runs(session):
    leaver = await _user(session, "leaver")
    stayer = await _user(session, "stayer")
    leaver_id, stayer_id = leaver.id, stayer.id

    # Add billing data for leaver to verify CASCADE deletion
    await get_or_create_account_plan(session, user_id=leaver_id)
    await get_or_create_usage_period(session, user_id=leaver_id)
    await session.commit()

    parent = Node(author_id=leaver.id, type=NodeType.FOLDER, name="parent")
    session.add(parent)
    await session.flush()
    child = Node(
        author_id=leaver.id,
        type=NodeType.DECK,
        parent_node_id=parent.id,
        name="child",
        visibility=Visibility.PUBLIC,
    )
    other_node = Node(author_id=stayer.id, type=NodeType.FOLDER, name="other")
    session.add_all([child, other_node])
    await session.flush()
    other_reference = Node(
        author_id=stayer.id,
        type=NodeType.REFERENCE,
        target_node_id=parent.id,
        name="reference",
    )
    session.add(other_reference)
    thread = AssistantThread(
        owner_id=leaver.id,
        title="thread",
        retention_deadline=datetime(2030, 1, 1, tzinfo=UTC),
    )
    session.add(thread)
    await session.flush()
    session.add(DeckSense(node_id=child.id, sense_id=42))
    await session.commit()
    ids = {
        "other": other_node.id,
        "reference": other_reference.id,
    }

    await delete_account(session, leaver_id)
    session.expire_all()

    assert await session.get(User, leaver_id) is None
    assert await session.get(User, stayer_id) is not None
    assert await session.get(Node, ids["other"]) is not None
    assert await session.get(Node, ids["reference"]) is None

    # Verify billing records were cascaded away
    assert (
        await session.scalar(
            text("SELECT count(*) FROM account_plans WHERE user_id = :id"),
            {"id": leaver_id},
        )
        == 0
    )
    assert (
        await session.scalar(
            text("SELECT count(*) FROM usage_periods WHERE user_id = :id"),
            {"id": leaver_id},
        )
        == 0
    )


async def test_delete_aborts_loudly_for_an_unremembered_user_fk(session):
    user = await _user(session, "sentinel")
    user_id = user.id
    await session.execute(
        text(
            "CREATE TABLE account_delete_sentinel ("
            "id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id))"
        )
    )
    await session.execute(
        text("INSERT INTO account_delete_sentinel (id, user_id) VALUES (:id, :user_id)"),
        {"id": uuid4(), "user_id": user_id},
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await delete_account(session, user_id)
    await session.rollback()
    assert await session.get(User, user_id) is not None

    await session.execute(text("DROP TABLE account_delete_sentinel"))
    await session.commit()


async def test_a_failed_external_deletion_leaves_the_account_intact(session, monkeypatch):
    """The external subject must go first, or a retry cannot converge.

    Clerk is the sign-in authority: while the subject exists, the next sign-in
    just-in-time provisions a fresh empty account. So a failure *after* the local
    rows were gone but *before* the subject was would resurrect the learner with an
    empty library. Ordering the Clerk call first means a failure leaves rows nobody
    can reach, which a retry still finishes.
    """
    from pycil.account import deletion as account_deletion

    user = await _user(session, "ordered")
    user.clerk_id = "user_ordered"
    await session.commit()
    user_id = user.id

    # No credential configured, so the external deletion refuses. The local rows
    # must survive: a half-deleted account is worse than an undeleted one.
    monkeypatch.setattr(account_deletion.settings, "clerk_secret_key", "")
    with pytest.raises(ServiceUnavailableError):
        await delete_account(session, user_id)
    await session.rollback()

    assert await session.get(User, user_id) is not None


async def test_a_deleted_subject_is_accepted_as_already_gone(session, monkeypatch):
    """Deletion is idempotent: a retry converges instead of failing forever.

    Clerk answers 404 once the subject is removed. Treating that as an error would
    make the second attempt of an interrupted deletion fail permanently, so it is
    accepted as the state we wanted.
    """
    from pycil.account import deletion as account_deletion

    user = await _user(session, "retry")
    user.clerk_id = "user_retry"
    await session.commit()
    user_id = user.id

    monkeypatch.setattr(account_deletion.settings, "clerk_secret_key", "test-key")

    import httpx
    from clerk_backend_api.models import ClerkErrors

    class _MockUsersGone:
        async def delete_async(self, *, user_id: str, **kwargs):
            raise ClerkErrors(data=None, raw_response=httpx.Response(404, text="not found"))

    class _MockClerkGone:
        def __init__(self, *args, **kwargs):
            self.users = _MockUsersGone()

    monkeypatch.setattr(account_deletion, "get_clerk_client", lambda: _MockClerkGone())

    await delete_account(session, user_id)
    # A raw count rather than session.get: the identity map still holds the
    # object the test created, so get() would answer from cache and prove nothing.
    remaining = await session.scalar(
        text("SELECT count(*) FROM users WHERE id = :user_id"), {"user_id": user_id}
    )
    assert remaining == 0


async def test_a_failed_external_deletion_is_surfaced_not_swallowed(session, monkeypatch):
    """A non-404 Clerk failure must raise, so the caller can retry.

    Swallowing it would report a successful deletion while the subject still
    exists — the exact state that lets the account come back.
    """
    from pycil.account import deletion as account_deletion

    user = await _user(session, "surfaced")
    user.clerk_id = "user_surfaced"
    await session.commit()
    user_id = user.id

    monkeypatch.setattr(account_deletion.settings, "clerk_secret_key", "test-key")

    import httpx
    from clerk_backend_api.models import ClerkErrors

    class _MockUsersFailed:
        async def delete_async(self, *, user_id: str, **kwargs):
            raise ClerkErrors(data=None, raw_response=httpx.Response(500, text="server error"))

    class _MockClerkFailed:
        def __init__(self, *args, **kwargs):
            self.users = _MockUsersFailed()

    monkeypatch.setattr(account_deletion, "get_clerk_client", lambda: _MockClerkFailed())

    with pytest.raises(ServiceUnavailableError, match="clerk_deletion_failed"):
        await delete_account(session, user_id)
    await session.rollback()
    assert await session.get(User, user_id) is not None
