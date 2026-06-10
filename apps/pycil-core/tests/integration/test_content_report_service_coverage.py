"""Direct unit coverage for content_report_service.

Exercises the service functions (not via routes) to pin:
- create() guard arms: invalid type, invalid/absent target, self-report, dup.
- create() comment path snapshot excerpt.
- list_for_admin() shape + status filter + limit clamp.
- resolve() guards: bad action, missing report, already-resolved.
- resolve() dismiss + delete_content (deck & comment) verify-then-delete arms.
- resolve() target_changed / target_gone defenses.
- count_reports_against().
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from pycil_core.services import content_report_service as crs


async def _make_deck(session, author_id, *, name="Reported Deck") -> str:
    row = (
        await session.execute(
            text(
                "INSERT INTO nodes (author_id, type, name, visibility) "
                "VALUES (:a, 'DECK'::node_type, :n, 'PUBLIC'::visibility) RETURNING id"
            ),
            {"a": author_id, "n": name},
        )
    ).one()
    await session.commit()
    return str(row.id)


async def _make_comment(session, author_id, *, body="offensive body") -> int:
    term = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": f"crs-{uuid4().hex[:6]}"},
        )
    ).one()
    definition = (
        await session.execute(
            text(
                "INSERT INTO definitions (term_id, synonyms, antonyms, notes) "
                "VALUES (:t, '{}', '{}', '{}') RETURNING id"
            ),
            {"t": term.id},
        )
    ).one()
    c = (
        await session.execute(
            text(
                "INSERT INTO definition_comments (definition_id, author_id, body) "
                "VALUES (:d, :a, :b) RETURNING id"
            ),
            {"d": definition.id, "a": author_id, "b": body},
        )
    ).one()
    await session.commit()
    return int(c.id)


# ── create() guards ───────────────────────────────────────────────────────


async def test_create_invalid_content_type_400(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await crs.create(
            session,
            reporter_user_id=UUID(str(test_user["id"])),
            content_type="banana",
            content_id="x",
            reason="spam",
            details=None,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid_content_type"


async def test_create_deck_invalid_uuid_400(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await crs.create(
            session,
            reporter_user_id=UUID(str(test_user["id"])),
            content_type="deck",
            content_id="not-a-uuid",
            reason="spam",
            details=None,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid_content_id"


async def test_create_deck_not_found_404(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await crs.create(
            session,
            reporter_user_id=UUID(str(test_user["id"])),
            content_type="deck",
            content_id=str(uuid4()),
            reason="spam",
            details=None,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "content_not_found"


async def test_create_comment_invalid_id_400(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await crs.create(
            session,
            reporter_user_id=UUID(str(test_user["id"])),
            content_type="comment",
            content_id="abc",
            reason="spam",
            details=None,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid_content_id"


async def test_create_comment_not_found_404(session, test_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await crs.create(
            session,
            reporter_user_id=UUID(str(test_user["id"])),
            content_type="comment",
            content_id="987654321",
            reason="spam",
            details=None,
        )
    assert exc.value.status_code == 404


async def test_create_self_report_400(session, test_user) -> None:
    deck_id = await _make_deck(session, test_user["id"], name="Mine")
    with pytest.raises(HTTPException) as exc:
        await crs.create(
            session,
            reporter_user_id=UUID(str(test_user["id"])),
            content_type="deck",
            content_id=deck_id,
            reason="x",
            details=None,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "cannot_report_own_content"


async def test_create_deck_happy_path_pending(session, test_user, second_user) -> None:
    deck_id = await _make_deck(session, second_user["id"])
    report_id = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details="please review",
    )
    await session.commit()
    assert report_id > 0
    row = (
        await session.execute(
            text(
                "SELECT status, content_type, node_id, target_owner_id, target_snapshot "
                "FROM content_reports WHERE id = :i"
            ),
            {"i": report_id},
        )
    ).one()
    assert row.status == "pending"
    assert row.content_type == "deck"
    assert str(row.node_id) == deck_id
    assert str(row.target_owner_id) == str(second_user["id"])


async def test_create_comment_snapshot_excerpt(session, test_user, second_user) -> None:
    long_body = "z" * 200
    comment_id = await _make_comment(session, second_user["id"], body=long_body)
    report_id = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="comment",
        content_id=str(comment_id),
        reason="abuse",
        details=None,
    )
    await session.commit()
    row = (
        await session.execute(
            text("SELECT comment_id, target_snapshot FROM content_reports WHERE id = :i"),
            {"i": report_id},
        )
    ).one()
    assert int(row.comment_id) == comment_id
    # excerpt truncated to 80 chars.
    assert len(row.target_snapshot["excerpt"]) == 80


async def test_create_duplicate_pending_409(session, test_user, second_user) -> None:
    deck_id = await _make_deck(session, second_user["id"])
    kwargs = dict(
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details=None,
    )
    await crs.create(session, **kwargs)
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await crs.create(session, **kwargs)
    assert exc.value.status_code == 409
    assert exc.value.detail == "duplicate_pending_report"


# ── list_for_admin() ────────────────────────────────────────────────────────


async def test_list_for_admin_filters_status_and_shape(
    session, test_user, second_user
) -> None:
    deck_id = await _make_deck(session, second_user["id"])
    rid = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details="d",
    )
    await session.commit()

    pending = await crs.list_for_admin(session, status_filter="pending", limit=10)
    assert len(pending) == 1
    item = pending[0]
    assert item["id"] == rid
    assert item["content_type"] == "deck"
    assert item["node_id"] == deck_id
    assert item["comment_id"] is None
    assert item["status"] == "pending"
    assert item["created_at"] is not None

    # Different filter → empty.
    assert await crs.list_for_admin(session, status_filter="actioned") == []


# ── resolve() guards ──────────────────────────────────────────────────────


async def test_resolve_invalid_action_400(session, admin_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await crs.resolve(
            session, report_id=1, admin_id=UUID(str(admin_user["id"])), action="nuke"
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "invalid_action"


async def test_resolve_missing_report_404(session, admin_user) -> None:
    with pytest.raises(HTTPException) as exc:
        await crs.resolve(
            session,
            report_id=999999,
            admin_id=UUID(str(admin_user["id"])),
            action="dismiss",
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "report_not_found"


async def test_resolve_already_resolved_409(
    session, test_user, second_user, admin_user
) -> None:
    deck_id = await _make_deck(session, second_user["id"])
    rid = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details=None,
    )
    await session.commit()
    await crs.resolve(
        session, report_id=rid, admin_id=UUID(str(admin_user["id"])), action="dismiss"
    )
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await crs.resolve(
            session,
            report_id=rid,
            admin_id=UUID(str(admin_user["id"])),
            action="dismiss",
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "report_already_resolved"


# ── resolve() actions ─────────────────────────────────────────────────────


async def test_resolve_dismiss_sets_status_and_note(
    session, test_user, second_user, admin_user
) -> None:
    deck_id = await _make_deck(session, second_user["id"])
    rid = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details=None,
    )
    await session.commit()
    out = await crs.resolve(
        session,
        report_id=rid,
        admin_id=UUID(str(admin_user["id"])),
        action="dismiss",
        note="not a violation",
    )
    await session.commit()
    assert out == {"report_id": rid, "status": "dismissed"}
    row = (
        await session.execute(
            text(
                "SELECT status, resolved_by, resolution FROM content_reports "
                "WHERE id = :i"
            ),
            {"i": rid},
        )
    ).one()
    assert row.status == "dismissed"
    assert str(row.resolved_by) == str(admin_user["id"])
    assert row.resolution == "not a violation"
    # Deck untouched.
    node = (
        await session.execute(
            text("SELECT deleted_at FROM nodes WHERE id = CAST(:i AS uuid)"),
            {"i": deck_id},
        )
    ).one()
    assert node.deleted_at is None


async def test_resolve_delete_deck_soft_deletes(
    session, test_user, second_user, admin_user
) -> None:
    deck_id = await _make_deck(session, second_user["id"])
    rid = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details=None,
    )
    await session.commit()
    out = await crs.resolve(
        session,
        report_id=rid,
        admin_id=UUID(str(admin_user["id"])),
        action="delete_content",
    )
    await session.commit()
    assert out["status"] == "actioned"
    node = (
        await session.execute(
            text("SELECT deleted_at FROM nodes WHERE id = CAST(:i AS uuid)"),
            {"i": deck_id},
        )
    ).one()
    assert node.deleted_at is not None


async def test_resolve_delete_comment_soft_deletes(
    session, test_user, second_user, admin_user
) -> None:
    comment_id = await _make_comment(session, second_user["id"])
    rid = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="comment",
        content_id=str(comment_id),
        reason="abuse",
        details=None,
    )
    await session.commit()
    out = await crs.resolve(
        session,
        report_id=rid,
        admin_id=UUID(str(admin_user["id"])),
        action="delete_content",
    )
    await session.commit()
    assert out["status"] == "actioned"
    row = (
        await session.execute(
            text("SELECT deleted_at FROM definition_comments WHERE id = :i"),
            {"i": comment_id},
        )
    ).one()
    assert row.deleted_at is not None


async def test_resolve_delete_deck_target_changed_409(
    session, test_user, second_user, admin_user
) -> None:
    """Owner snapshot mismatch (target re-parented to another author) → 409."""
    deck_id = await _make_deck(session, second_user["id"])
    rid = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details=None,
    )
    await session.commit()
    # Mutate the deck's author after the snapshot was taken.
    await session.execute(
        text("UPDATE nodes SET author_id = :a WHERE id = CAST(:i AS uuid)"),
        {"a": test_user["id"], "i": deck_id},
    )
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await crs.resolve(
            session,
            report_id=rid,
            admin_id=UUID(str(admin_user["id"])),
            action="delete_content",
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "target_changed"


async def test_resolve_delete_deck_target_gone_409(
    session, test_user, second_user, admin_user
) -> None:
    deck_id = await _make_deck(session, second_user["id"])
    rid = await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details=None,
    )
    await session.commit()
    # Hard-delete the node row so the verify re-fetch misses.
    await session.execute(
        text("DELETE FROM nodes WHERE id = CAST(:i AS uuid)"), {"i": deck_id}
    )
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await crs.resolve(
            session,
            report_id=rid,
            admin_id=UUID(str(admin_user["id"])),
            action="delete_content",
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "target_gone"


# ── count_reports_against() ─────────────────────────────────────────────────


async def test_count_reports_against(session, test_user, second_user) -> None:
    owner = UUID(str(second_user["id"]))
    assert await crs.count_reports_against(session, owner_id=owner) == 0
    deck_id = await _make_deck(session, second_user["id"])
    await crs.create(
        session,
        reporter_user_id=UUID(str(test_user["id"])),
        content_type="deck",
        content_id=deck_id,
        reason="spam",
        details=None,
    )
    await session.commit()
    assert await crs.count_reports_against(session, owner_id=owner) == 1
