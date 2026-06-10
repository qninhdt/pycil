"""Direct unit coverage for user_service.

Pins upsert idempotency, token-version revocation/check, ban/unban,
soft-delete + hard-delete-expired, search/summary/role helpers, last-admin
guard, and admin detail aggregations (recent_jobs, mastery_distribution).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from pycil_core.services import user_service


# ── upsert_user ─────────────────────────────────────────────────────────────


async def test_upsert_inserts_new_user(session) -> None:
    email = f"new-{uuid4().hex[:8]}@example.test"
    result = await user_service.upsert_user(
        session, email=email, name="Newbie", image="http://img/a.png"
    )
    assert isinstance(result.user_id, UUID)
    assert result.role == "user"
    assert result.token_version == 0
    row = (
        await session.execute(
            text("SELECT name, image FROM users WHERE id = :i"),
            {"i": result.user_id},
        )
    ).one()
    assert row.name == "Newbie"
    assert row.image == "http://img/a.png"


async def test_upsert_updates_existing_and_coalesces_nulls(session) -> None:
    email = f"up-{uuid4().hex[:8]}@example.test"
    first = await user_service.upsert_user(
        session, email=email, name="Original", image="http://img/orig.png"
    )
    # Second upsert with name=None must keep the existing name (coalesce).
    second = await user_service.upsert_user(
        session, email=email, name=None, image="http://img/new.png"
    )
    assert second.user_id == first.user_id
    row = (
        await session.execute(
            text("SELECT name, image FROM users WHERE id = :i"),
            {"i": first.user_id},
        )
    ).one()
    assert row.name == "Original"  # coalesced, not overwritten with NULL
    assert row.image == "http://img/new.png"


# ── token_version check ─────────────────────────────────────────────────────


async def test_token_version_check_matches(session, test_user) -> None:
    out = await user_service.get_with_token_version_check(
        session, user_id=UUID(str(test_user["id"])), token_version=0
    )
    assert out is not None
    assert out["email"] == test_user["email"]
    assert out["role"] == "user"
    assert out["banned_at"] is None


async def test_token_version_check_mismatch_returns_none(session, test_user) -> None:
    out = await user_service.get_with_token_version_check(
        session, user_id=UUID(str(test_user["id"])), token_version=99
    )
    assert out is None


async def test_token_version_check_unknown_user_none(session) -> None:
    out = await user_service.get_with_token_version_check(
        session, user_id=uuid4(), token_version=0
    )
    assert out is None


# ── revoke / bump ───────────────────────────────────────────────────────────


async def test_revoke_tokens_bumps_version(session, test_user) -> None:
    new_v = await user_service.revoke_tokens(
        session, user_id=UUID(str(test_user["id"]))
    )
    assert new_v == 1
    # Old token version now rejected.
    assert (
        await user_service.get_with_token_version_check(
            session, user_id=UUID(str(test_user["id"])), token_version=0
        )
        is None
    )


async def test_revoke_tokens_unknown_user_raises(session) -> None:
    with pytest.raises(LookupError):
        await user_service.revoke_tokens(session, user_id=uuid4())


async def test_bump_token_version_no_commit(session, test_user) -> None:
    new_v = await user_service.bump_token_version(
        session, user_id=UUID(str(test_user["id"]))
    )
    assert new_v == 1


async def test_bump_token_version_unknown_raises(session) -> None:
    with pytest.raises(LookupError):
        await user_service.bump_token_version(session, user_id=uuid4())


# ── soft delete + hard delete expired ───────────────────────────────────────


async def test_soft_delete_sets_deleted_at_and_revokes(session, test_user) -> None:
    await user_service.soft_delete_user(
        session, user_id=UUID(str(test_user["id"]))
    )
    row = (
        await session.execute(
            text("SELECT deleted_at, token_version FROM users WHERE id = :i"),
            {"i": test_user["id"]},
        )
    ).one()
    assert row.deleted_at is not None
    assert row.token_version == 1
    assert await user_service.is_soft_deleted(session, email=test_user["email"]) is True


async def test_is_soft_deleted_false_for_active(session, test_user) -> None:
    assert (
        await user_service.is_soft_deleted(session, email=test_user["email"]) is False
    )


async def test_hard_delete_expired_only_old(session) -> None:
    old_email = f"old-{uuid4().hex[:6]}@x.test"
    recent_email = f"recent-{uuid4().hex[:6]}@x.test"
    old_cut = datetime.now(UTC) - timedelta(days=20)
    recent_cut = datetime.now(UTC) - timedelta(days=2)
    await session.execute(
        text(
            "INSERT INTO users (email, name, deleted_at) VALUES (:e, 'Old', :d)"
        ),
        {"e": old_email, "d": old_cut},
    )
    await session.execute(
        text(
            "INSERT INTO users (email, name, deleted_at) VALUES (:e, 'Recent', :d)"
        ),
        {"e": recent_email, "d": recent_cut},
    )
    await session.commit()

    deleted = await user_service.hard_delete_expired(session)
    assert deleted == 1
    remaining = (
        await session.execute(
            text("SELECT email FROM users WHERE email IN (:a, :b)"),
            {"a": old_email, "b": recent_email},
        )
    ).all()
    emails = {r.email for r in remaining}
    assert old_email not in emails
    assert recent_email in emails


# ── ban / unban ─────────────────────────────────────────────────────────────


async def test_set_ban_sets_fields_bumps_version(session, test_user) -> None:
    ok = await user_service.set_ban(
        session, user_id=UUID(str(test_user["id"])), reason="spamming"
    )
    await session.commit()
    assert ok is True
    row = (
        await session.execute(
            text(
                "SELECT banned_at, ban_reason, token_version FROM users WHERE id = :i"
            ),
            {"i": test_user["id"]},
        )
    ).one()
    assert row.banned_at is not None
    assert row.ban_reason == "spamming"
    assert row.token_version == 1


async def test_set_ban_unknown_user_false(session) -> None:
    ok = await user_service.set_ban(session, user_id=uuid4(), reason="x")
    assert ok is False


async def test_clear_ban_keeps_token_version(session, test_user) -> None:
    await user_service.set_ban(
        session, user_id=UUID(str(test_user["id"])), reason="x"
    )
    await session.commit()
    ok = await user_service.clear_ban(session, user_id=UUID(str(test_user["id"])))
    await session.commit()
    assert ok is True
    row = (
        await session.execute(
            text(
                "SELECT banned_at, ban_reason, token_version FROM users WHERE id = :i"
            ),
            {"i": test_user["id"]},
        )
    ).one()
    assert row.banned_at is None
    assert row.ban_reason is None
    # Unban does NOT reset the bump done at ban time.
    assert row.token_version == 1


# ── role / admin guard ──────────────────────────────────────────────────────


async def test_get_role(session, test_user, admin_user) -> None:
    assert await user_service.get_role(
        session, user_id=UUID(str(test_user["id"]))
    ) == "user"
    assert await user_service.get_role(
        session, user_id=UUID(str(admin_user["id"]))
    ) == "admin"
    assert await user_service.get_role(session, user_id=uuid4()) is None


async def test_count_active_admins(session, admin_user, test_user) -> None:
    assert await user_service.count_active_admins(session) == 1
    # Ban the admin → no longer counted.
    await user_service.set_ban(
        session, user_id=UUID(str(admin_user["id"])), reason="x"
    )
    await session.commit()
    assert await user_service.count_active_admins(session) == 0


# ── search / summary ────────────────────────────────────────────────────────


async def test_search_users_filter_by_query(session, test_user, second_user) -> None:
    # Filter narrows to the matching email.
    results = await user_service.search_users(
        session, q=test_user["email"][:10]
    )
    assert any(r["email"] == test_user["email"] for r in results)
    assert all(r["banned"] is False for r in results)


async def test_search_users_excludes_soft_deleted(session, test_user) -> None:
    await user_service.soft_delete_user(
        session, user_id=UUID(str(test_user["id"]))
    )
    results = await user_service.search_users(session)
    assert all(r["id"] != str(test_user["id"]) for r in results)


async def test_get_user_summary(session, test_user) -> None:
    summary = await user_service.get_user_summary(
        session, user_id=UUID(str(test_user["id"]))
    )
    assert summary is not None
    assert summary["email"] == test_user["email"]
    assert summary["role"] == "user"
    assert summary["banned"] is False
    assert summary["token_version"] == 0


async def test_get_user_summary_unknown_none(session) -> None:
    assert await user_service.get_user_summary(session, user_id=uuid4()) is None


# ── recent_jobs / mastery_distribution ──────────────────────────────────────


async def test_recent_jobs(session, test_user) -> None:
    for i in range(2):
        await session.execute(
            text(
                "INSERT INTO jobs (type, status, created_by_user_id) "
                "VALUES (:t, 'completed', :u)"
            ),
            {"t": f"generate_term", "u": test_user["id"]},
        )
    await session.commit()
    jobs = await user_service.recent_jobs(
        session, user_id=UUID(str(test_user["id"])), limit=5
    )
    assert len(jobs) == 2
    assert all(j["type"] == "generate_term" for j in jobs)
    assert all(j["status"] == "completed" for j in jobs)


async def test_mastery_distribution(session, test_user) -> None:
    # Two definitions at mastery_level 4 (seed factory default), one at level 0.
    term = (
        await session.execute(
            text(
                "INSERT INTO terms (value, type) "
                "VALUES (:v, 'SINGLE_WORD'::term_type) RETURNING id"
            ),
            {"v": f"md-{uuid4().hex[:6]}"},
        )
    ).one()
    def_ids = []
    for sense_index in range(3):
        d = (
            await session.execute(
                text(
                    "INSERT INTO definitions "
                    "(term_id, sense_index, synonyms, antonyms, notes) "
                    "VALUES (:t, :s, '{}', '{}', '{}') RETURNING id"
                ),
                {"t": term.id, "s": sense_index},
            )
        ).one()
        def_ids.append(d.id)
    # Insert stats with explicit mastery_level.
    await session.execute(
        text(
            "INSERT INTO user_term_stats (user_id, definition_id, mastery_level) "
            "VALUES (:u, :d, 4)"
        ),
        {"u": test_user["id"], "d": def_ids[0]},
    )
    await session.execute(
        text(
            "INSERT INTO user_term_stats (user_id, definition_id, mastery_level) "
            "VALUES (:u, :d, 4)"
        ),
        {"u": test_user["id"], "d": def_ids[1]},
    )
    await session.execute(
        text(
            "INSERT INTO user_term_stats (user_id, definition_id, mastery_level) "
            "VALUES (:u, :d, 0)"
        ),
        {"u": test_user["id"], "d": def_ids[2]},
    )
    await session.commit()

    dist = await user_service.mastery_distribution(
        session, user_id=UUID(str(test_user["id"]))
    )
    assert dist == {"4": 2, "0": 1}
