"""Durable SSE subscribe-proxy authorization and snapshot recovery."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from shared.realtime.channels import ASYNC_TASK_PREFIX

from pycil.auth.models import User
from pycil.realtime.application.subscriptions import SubscribeProxyRequest, authorize_subscription
from pycil.realtime.router import _current_token_version
from pycil.tasks.application import service
from pycil.tasks.domain.vocabulary import TASK_KIND_GRADING
from pycil.tasks.infra.models import AsyncTaskStatus

pytestmark = pytest.mark.asyncio

# The production token-version lookup. `authorize_subscription` takes it as a
# parameter rather than importing `auth`, which is what keeps `realtime` off the
# `auth <-> realtime` cycle; passing the real one here means these tests cover the
# wiring too, not just the authorizer in isolation.
_lookup = _current_token_version


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _task(session, user: User):
    return await service.submit_or_join(
        session,
        kind=TASK_KIND_GRADING,
        server_work_key="grading:response-1",
        requester_id=user.id,
        command_kind="grading.submit",
        command_id="command-1",
        provenance="response-owner",
    )


def _request(user: User, task_id, **meta) -> SubscribeProxyRequest:
    return SubscribeProxyRequest(
        user=str(user.id),
        channel=f"{ASYNC_TASK_PREFIX}{task_id}",
        meta={
            "tokenVersion": user.token_version,
            "expiresAt": int(datetime.now(UTC).timestamp()) + 60,
            **meta,
        },
    )


async def test_subscribe_returns_current_persisted_snapshot(session):
    user = await _user(session, "snapshot-subscribe@example.com")
    submission = await _task(session, user)

    result = await authorize_subscription(session, _request(user, submission.task.id), _lookup)

    assert result["result"]["data"] == {
        "schema": "async-task.v1",
        "eventId": result["result"]["data"]["eventId"],
        "taskId": str(submission.task.id),
        "kind": TASK_KIND_GRADING,
        "status": "queued",
        "version": 1,
        "result": None,
        "errorCode": None,
    }


async def test_subscribe_rejects_foreign_or_revoked_interest(session):
    owner = await _user(session, "owner-subscribe@example.com")
    outsider = await _user(session, "outsider-subscribe@example.com")
    submission = await _task(session, owner)

    outsider_request = _request(outsider, submission.task.id)
    assert await authorize_subscription(session, outsider_request, _lookup) == {
        "error": {"code": 103, "message": "permission denied"}
    }
    submission.interest.revoked_at = datetime.now(UTC)
    await session.commit()
    assert await authorize_subscription(session, _request(owner, submission.task.id), _lookup) == {
        "error": {"code": 103, "message": "permission denied"}
    }


async def test_subscribe_rejects_bad_channel_token_version_and_expiry(session):
    user = await _user(session, "invalid-subscribe@example.com")
    submission = await _task(session, user)

    stale = _request(user, submission.task.id, tokenVersion=99)
    result = await authorize_subscription(session, stale, _lookup)
    assert result == {
        "error": {"code": 103, "message": "permission denied"}
    }
    assert await authorize_subscription(
        session,
        SubscribeProxyRequest(
            user=str(user.id), channel="async:not-a-uuid", meta={"tokenVersion": 0, "expiresAt": 1}
        ),
        _lookup,
    ) == {"error": {"code": 103, "message": "permission denied"}}


async def test_interest_created_by_a_route_carries_an_expiry(session):
    """B2: both production callers omitted `expires_at`, so nothing ever lapsed.

    `authorize_subscription` treats `expires_at IS NULL` as "never expires", and
    neither `content/router.py` nor `learning/answering.py` passed a value. Measured
    on the live database: 103 of 103 interests had a NULL expiry, none had
    `revoked_at`, and all 103 pointed at tasks that had already reached a terminal
    state — 103 channels authorized forever.
    """
    user = await _user(session, "expiry-default@example.com")
    submission = await _task(session, user)

    assert submission.interest.expires_at is not None, (
        "submit_or_join must give every interest a bounded lifetime"
    )
    # The bound has to outlive the work: four attempts at a 120s lease, plus retry
    # backoff, plus the reconciler's own polling interval, is 756s.
    lifetime = (submission.interest.expires_at - datetime.now(UTC)).total_seconds()
    assert lifetime > 756, f"an interest must outlive the task it watches, got {lifetime}s"


async def test_a_lapsed_interest_is_denied(session):
    """An expiry that is not enforced is not an expiry."""
    user = await _user(session, "expiry-lapsed@example.com")
    submission = await _task(session, user)

    submission.interest.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    assert await authorize_subscription(session, _request(user, submission.task.id), _lookup) == {
        "error": {"code": 103, "message": "permission denied"}
    }


async def test_a_terminal_task_keeps_a_grace_window_then_lapses(session):
    """Terminal must shorten the window without destroying the result.

    Revoking on the terminal transition looks right and loses data. Subscribing *is*
    the read — there is no REST route that returns a task — and the client persists
    only unsettled ids, so a tab that was closed when the task finished re-subscribes
    on the next mount to collect the outcome. A revoked interest answers that with
    code 103, which `markStale` records with no recovery path.

    So the terminal transition clamps the expiry to a grace window instead: long
    enough to hand over the result, short enough that the channel is not authorized
    indefinitely.
    """
    user = await _user(session, "expiry-terminal@example.com")
    submission = await _task(session, user)
    original_expiry = submission.interest.expires_at

    settled = await service.claim_task(session, submission.task.id, "worker-a")
    assert settled is not None
    await service.transition_task(
        session,
        submission.task.id,
        lease_token=settled.lease_token,
        lease_fence=settled.lease_fence,
        status=AsyncTaskStatus.SUCCEEDED,
        result={"wordId": 1},
    )
    await session.refresh(submission.interest)

    assert submission.interest.expires_at < original_expiry, (
        "a terminal task must shorten its interest window"
    )
    # The result is still readable, which is the whole point of the grace window.
    authorized = await authorize_subscription(session, _request(user, submission.task.id), _lookup)
    assert authorized["result"]["data"]["status"] == "succeeded"

    # And it does lapse.
    submission.interest.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    assert await authorize_subscription(session, _request(user, submission.task.id), _lookup) == {
        "error": {"code": 103, "message": "permission denied"}
    }


async def test_subscribe_expiry_is_clamped_to_the_interest_not_the_token(session):
    """Centrifugo enforces `expire_at`; returning the token's value ignored revocation.

    The connection token lives 900s and has no revocation list, so a subscription
    authorized one second before an interest lapses survived on Centrifugo's clock
    for up to 15 further minutes. The proxy must return whichever bound comes first.
    """
    user = await _user(session, "expiry-clamp@example.com")
    submission = await _task(session, user)
    interest_deadline = datetime.now(UTC) + timedelta(seconds=30)
    submission.interest.expires_at = interest_deadline
    await session.commit()

    token_expiry = int(datetime.now(UTC).timestamp()) + 900
    long_lived = _request(user, submission.task.id, expiresAt=token_expiry)
    result = await authorize_subscription(session, long_lived, _lookup)

    assert result["result"]["expire_at"] == int(interest_deadline.timestamp()), (
        "expire_at must be clamped to the interest when it lapses first"
    )
    assert result["result"]["expire_at"] < token_expiry


async def test_the_terminal_transition_does_not_unsubscribe_from_centrifugo(session, monkeypatch):
    """Recorded decision: closing the window is expiry's job, not unsubscribe's.

    An explicit Centrifugo `unsubscribe` on the terminal transition was considered
    and rejected: it worked (verified against v6.8.3), but calling it here would
    cut the connection before the outbox has published the terminal snapshot.
    `transition_task` and `dispatch_task_outbox` are separate,
    asynchronous paths: the transition only enqueues an outbox row, and the cron
    relay publishes it up to a minute later. Unsubscribing first destroys exactly
    the handover the grace window exists to protect.

    So the window is closed by the clamped expiry instead, and this pins that
    choice: a future change that adds the call back fails here.

    The client no longer exposes an `unsubscribe_channel` at all — it was deleted
    as uncalled — so the seam is asserted by spying on the transport instead of on
    a named method. That is the stronger check: it fails for any new HTTP call the
    transition makes to Centrifugo, not only for one spelled a particular way.

    The spy is installed as the process adapter rather than by patching
    `httpx.AsyncClient`. `CentrifugoControl` builds its client once in `__init__`,
    so replacing the class afterwards intercepts nothing and the test would pass
    without observing anything at all.
    """
    from pycil.ports import centrifugo as realtime_client

    calls: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        raise AssertionError(f"the terminal transition called Centrifugo at {request.url}")

    spy = realtime_client.CentrifugoControl(
        httpx.AsyncClient(transport=httpx.MockTransport(record))
    )
    monkeypatch.setattr(realtime_client, "_control", spy)

    user = await _user(session, "terminal-no-unsubscribe@example.com")
    submission = await _task(session, user)
    claimed = await service.claim_task(session, submission.task.id, "worker-a")
    assert claimed is not None
    await service.transition_task(
        session,
        submission.task.id,
        lease_token=claimed.lease_token,
        lease_fence=claimed.lease_fence,
        status=AsyncTaskStatus.SUCCEEDED,
        result={"wordId": 1},
    )

    assert calls == [], (
        "the terminal transition must not unsubscribe before the outbox publishes"
    )


async def test_the_terminal_clamp_only_shortens_never_extends(session):
    """The clamp must not resurrect an interest that is already closer to death.

    A retried task settles on a later attempt, and a caller may have asked for a
    shorter window than the default. Writing the grace deadline unconditionally
    would move those expiries *later* — turning the terminal transition into an
    extension, which is the opposite of what B2 is about. Worse, a lapsed interest
    would come back to life.
    """
    user = await _user(session, "clamp-only-shortens@example.com")
    submission = await _task(session, user)
    # Already closer than the grace window, and already lapsed.
    already_lapsed = datetime.now(UTC) - timedelta(seconds=5)
    submission.interest.expires_at = already_lapsed
    await session.commit()

    claimed = await service.claim_task(session, submission.task.id, "worker-a")
    assert claimed is not None
    await service.transition_task(
        session,
        submission.task.id,
        lease_token=claimed.lease_token,
        lease_fence=claimed.lease_fence,
        status=AsyncTaskStatus.SUCCEEDED,
        result={"wordId": 1},
    )
    await session.refresh(submission.interest)

    assert submission.interest.expires_at == already_lapsed, (
        "settling a task must not extend an interest that expires sooner"
    )
    # And it stays denied, rather than being revived by its own task finishing.
    assert await authorize_subscription(session, _request(user, submission.task.id), _lookup) == {
        "error": {"code": 103, "message": "permission denied"}
    }
