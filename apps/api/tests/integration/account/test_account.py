"""Account invariants."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from pycil.account.credit import (
    CREDIT_KIND_RUBRIC,
    CreditExhaustedError,
    balance,
    debit,
    require_balance,
    settle_agent_turn,
    snapshot,
)
from pycil.account.models import CreditDebit, UserCredit
from pycil.account.plans import PLANS, AccountPlan, period_grant
from pycil.account.service import delete_account, export_account
from pycil.assistant.infra.models import AssistantThread
from pycil.auth.models import User
from pycil.common.errors import ServiceUnavailableError
from pycil.content.infra.models import DeckSense
from pycil.hierarchy.domain.vocabulary import NodeType, Visibility
from pycil.hierarchy.infra.models import Node

pytestmark = pytest.mark.asyncio


async def _user(session, prefix: str = "account") -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.test")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_plan_shape_has_two_tiers_and_an_allowance():
    assert set(PLANS) == {AccountPlan.free, AccountPlan.pro}
    assert PLANS[AccountPlan.free].period_grant < PLANS[AccountPlan.pro].period_grant


async def test_debit_rolls_elapsed_period_and_is_idempotent(session):
    user = await _user(session)
    now = datetime(2030, 1, 31, tzinfo=UTC)
    session.add(
        UserCredit(
            user_id=user.id,
            plan=AccountPlan.free,
            period_anchor=now - timedelta(days=31),
            period_start=now - timedelta(days=31),
            period_used=period_grant(AccountPlan.free),
            topup_balance=30,
        )
    )
    await session.commit()
    reference = uuid4()

    first = await debit(
        session, user.id, kind=CREDIT_KIND_RUBRIC, reference_id=reference, amount=10, now=now
    )
    await session.commit()
    second = await debit(
        session, user.id, kind=CREDIT_KIND_RUBRIC, reference_id=reference, amount=10, now=now
    )
    await session.commit()

    current = await snapshot(session, user.id)
    assert first.id == second.id
    assert current.period_start == now, "the elapsed month rolled the period forward"
    assert current.period_used == 10
    assert current.topup_balance == 30
    assert current.balance == period_grant(AccountPlan.free) - 10 + 30
    assert (
        await session.scalar(
            text("SELECT count(*) FROM credit_debits WHERE user_id = :user_id"),
            {"user_id": user.id},
        )
        == 1
    )


async def test_resumed_agent_turn_updates_one_cumulative_debit(session):
    user = await _user(session, "assistant-resume")
    reference = uuid4()
    now = datetime(2030, 4, 12, tzinfo=UTC)

    first = await settle_agent_turn(
        session,
        user.id,
        reference_id=reference,
        amount=120,
        details={"status": "interrupted", "usage": {"version": 1, "calls": []}},
        now=now,
    )
    await session.commit()
    resumed = await settle_agent_turn(
        session,
        user.id,
        reference_id=reference,
        amount=350,
        details={"status": "completed", "usage": {"version": 1, "calls": [1]}},
        now=now,
    )
    await session.commit()
    replay = await settle_agent_turn(
        session,
        user.id,
        reference_id=reference,
        amount=350,
        details={"status": "completed", "usage": {"version": 1, "calls": [1]}},
        now=now,
    )
    await session.commit()

    current = await snapshot(session, user.id, now=now)
    assert first.id == resumed.id == replay.id
    assert replay.amount == 350
    assert current.period_used == 350
    assert replay.details["period_charges"] == {current.period_start.isoformat(): 350}
    assert await session.scalar(
        select(CreditDebit).where(CreditDebit.reference_id == reference)
    ) is not None


async def test_submit_gate_is_typed_and_balance_is_one_pool(session):
    user = await _user(session)
    assert await balance(session, user.id) == period_grant(AccountPlan.free)
    await require_balance(session, user.id, amount=1)

    row = await session.get(UserCredit, user.id)
    assert row is not None
    row.period_used = period_grant(AccountPlan.free)
    row.topup_balance = 0
    await session.commit()
    with pytest.raises(CreditExhaustedError, match="credit_exhausted"):
        await require_balance(session, user.id, amount=1)


async def test_reads_reflect_elapsed_rollover_before_any_debit(session):
    user = await _user(session)
    now = datetime.now(UTC)
    session.add(
        UserCredit(
            user_id=user.id,
            plan=AccountPlan.free,
            period_anchor=now - timedelta(days=95),
            period_start=now - timedelta(days=95),
            period_used=period_grant(AccountPlan.free),
            topup_balance=0,
        )
    )
    await session.commit()

    # The prior period was fully spent, but it has elapsed. A read must show the
    # fresh grant so a returning learner is not locked out: the sampler gates L4
    # off a zero balance, and the L4 debit is the only thing that would roll it.
    assert await balance(session, user.id) == period_grant(AccountPlan.free)
    await require_balance(session, user.id, amount=1)


async def test_the_allowance_is_clamped_for_display_but_stays_signed(session):
    """An admitted turn may overshoot; the UI must not show a negative allowance."""
    user = await _user(session)
    session.add(
        UserCredit(
            user_id=user.id,
            plan=AccountPlan.free,
            period_anchor=datetime.now(UTC),
            period_start=datetime.now(UTC),
            period_used=0,
            topup_balance=0,
        )
    )
    await session.commit()

    await debit(
        session,
        user.id,
        kind=CREDIT_KIND_RUBRIC,
        reference_id=uuid4(),
        amount=period_grant(AccountPlan.free) + 250,
    )
    await session.commit()

    current = await snapshot(session, user.id)
    assert current.balance == -250, "the ledger records the overshoot it actually incurred"
    assert current.available == 0, "display clamps, the stored balance does not"
    with pytest.raises(CreditExhaustedError):
        await require_balance(session, user.id, amount=1)


async def test_export_contains_plan_and_credit_but_no_dictionary_rows(session):
    user = await _user(session)
    session.add(UserCredit(user_id=user.id, plan=AccountPlan.pro, topup_balance=40))
    await session.commit()

    exported = await export_account(session, user.id)

    assert exported["plan"] == AccountPlan.pro
    assert exported["credit"]["topup_balance"] == 40
    assert "dictionary" not in exported
    assert "words" not in exported
    assert "senses" not in exported["learning"]


async def test_delete_is_ordered_and_keeps_nodes_and_runs(session):
    leaver = await _user(session, "leaver")
    stayer = await _user(session, "stayer")
    leaver_id, stayer_id = leaver.id, stayer.id
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
    from pycil.account import service as account_service

    user = await _user(session, "ordered")
    user.clerk_id = "user_ordered"
    await session.commit()
    user_id = user.id

    # No credential configured, so the external deletion refuses. The local rows
    # must survive: a half-deleted account is worse than an undeleted one.
    monkeypatch.setattr(account_service.settings, "clerk_secret_key", "")
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
    from pycil.account import service as account_service

    user = await _user(session, "retry")
    user.clerk_id = "user_retry"
    await session.commit()
    user_id = user.id

    monkeypatch.setattr(account_service.settings, "clerk_secret_key", "test-key")

    class _Response:
        status_code = 404

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def delete(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(account_service.httpx, "AsyncClient", lambda **kwargs: _Client())

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
    from pycil.account import service as account_service

    user = await _user(session, "surfaced")
    user.clerk_id = "user_surfaced"
    await session.commit()
    user_id = user.id

    monkeypatch.setattr(account_service.settings, "clerk_secret_key", "test-key")

    class _Response:
        status_code = 500

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def delete(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(account_service.httpx, "AsyncClient", lambda **kwargs: _Client())

    with pytest.raises(ServiceUnavailableError, match="clerk_deletion_failed"):
        await delete_account(session, user_id)
    await session.rollback()
    assert await session.get(User, user_id) is not None
