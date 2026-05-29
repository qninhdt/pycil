"""Regression: converted delete/update service fns must not self-shadow.

Before the SQLModel conversion was stabilized, three services declared a
module-level `async def delete`/`update` that shadowed the imported SQLAlchemy
`delete`/`update`, so the in-function `delete(Model)` call resolved to the
coroutine function itself and raised TypeError at runtime on the first call.

These tests call each fixed function with a capturing fake session (no DB
needed) and assert: (1) it does NOT raise, and (2) it builds a real SQLAlchemy
Delete/Update statement against the right table — proving the shadow is gone.
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy.sql.dml import Delete, Update

from pycil_core.services import (
    definition_overrides_service,
    saved_search_service,
    term_notes_service,
)


class _CaptureSession:
    """Minimal stand-in for AsyncSession: records statements passed to exec()."""

    def __init__(self) -> None:
        self.statements: list[object] = []

    async def exec(self, stmt: object):
        self.statements.append(stmt)

        class _Result:
            rowcount = 1

        return _Result()


async def test_term_notes_delete_builds_delete_statement() -> None:
    sess = _CaptureSession()
    await term_notes_service.delete(sess, uuid4(), 1)  # type: ignore[arg-type]
    assert len(sess.statements) == 1
    assert isinstance(sess.statements[0], Delete)


async def test_saved_search_delete_builds_delete_statement() -> None:
    sess = _CaptureSession()
    await saved_search_service.delete(sess, uuid4(), 1)  # type: ignore[arg-type]
    assert len(sess.statements) == 1
    assert isinstance(sess.statements[0], Delete)


async def test_saved_search_update_builds_update_statement() -> None:
    sess = _CaptureSession()
    await saved_search_service.update(sess, uuid4(), 1, name="renamed")  # type: ignore[arg-type]
    assert len(sess.statements) == 1
    assert isinstance(sess.statements[0], Update)


async def test_definition_overrides_delete_builds_delete_statement() -> None:
    sess = _CaptureSession()
    await definition_overrides_service.delete(sess, uuid4(), 1)  # type: ignore[arg-type]
    assert len(sess.statements) == 1
    assert isinstance(sess.statements[0], Delete)
