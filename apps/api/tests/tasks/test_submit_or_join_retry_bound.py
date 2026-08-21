"""A commit-time receipt race must not recurse without a bound.

``submit_or_join`` retries itself when the commit hits ``IntegrityError``, which
is how it defers to a racing command replay's receipt. The retry is correct; an
unbounded number of them is not. If the condition that caused the IntegrityError
does not clear — a receipt that is committed but not visible to this session, or
a persistent constraint violation elsewhere in the same flush — the function
recurses until Python raises ``RecursionError``.

That failure mode is worse than the race it guards. ``main.py`` registers
handlers for ``AppError``, ``RequestValidationError`` and ``HTTPException`` only,
so a ``RecursionError`` escapes as a bare 500 with no error code, no structured
body, and a stack trace thousands of frames deep in the logs.

These tests force the pathological case by making the commit raise every time,
then assert the function gives up with a typed error after a bounded number of
attempts.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from pycil.auth.models import User
from pycil.common.errors import AppError
from pycil.tasks.application import service
from pycil.tasks.domain.vocabulary import TASK_KIND_WORD

pytestmark = pytest.mark.asyncio


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _always_conflicting_commit(session, counter: list[int]):
    """Replace commit with one that always reports a receipt conflict.

    Rollback stays real so the session remains usable across attempts; only the
    commit is poisoned. That mirrors the shape of the production race rather than
    breaking the session outright.
    """
    original_commit = session.commit

    async def commit() -> None:
        counter.append(1)
        raise IntegrityError(
            "INSERT INTO async_command_receipts",
            {},
            Exception("duplicate key value violates unique constraint"),
        )

    session.commit = commit
    return original_commit


async def test_persistent_receipt_conflict_gives_up_instead_of_recursing(session):
    """A commit that always conflicts must raise a typed error, not RecursionError."""
    user = await _user(session, "recursion-bound@example.com")
    attempts: list[int] = []
    _always_conflicting_commit(session, attempts)

    with pytest.raises(AppError) as exc_info:
        await service.submit_or_join(
            session,
            kind=TASK_KIND_WORD,
            server_work_key="word:recursion:probe",
            requester_id=user.id,
            command_kind="word.generate",
            command_id="recursion-probe-command",
            provenance="word-search",
        )

    # A typed AppError is what main.py can render as a structured response.
    # RecursionError is not, and neither is a bare IntegrityError.
    assert exc_info.value.code == "async_command_conflict"

    # The bound is what this test exists to prove. Python's default recursion
    # limit is ~1000; anything near it means the retry is effectively unbounded.
    assert len(attempts) <= 5, f"retried {len(attempts)} times — not bounded"


async def test_recursion_error_is_never_the_failure_mode(session):
    """Guard the specific exception type that would escape as a bare 500."""
    user = await _user(session, "no-recursion-error@example.com")
    attempts: list[int] = []
    _always_conflicting_commit(session, attempts)

    try:
        await service.submit_or_join(
            session,
            kind=TASK_KIND_WORD,
            server_work_key="word:no-recursion:probe",
            requester_id=user.id,
            command_kind="word.generate",
            command_id="no-recursion-command",
            provenance="word-search",
        )
    except RecursionError:  # pragma: no cover - the defect this test locks out
        pytest.fail("submit_or_join recursed until the interpreter stopped it")
    except AppError:
        pass  # giving up with a typed error is the intended behaviour
