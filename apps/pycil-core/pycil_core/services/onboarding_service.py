"""First-login onboarding: seed a sample folder + deck with pre-enriched terms.

Idempotent — checks for existing user_nodes rows before seeding so re-login
or session cookie refresh never double-seeds.
"""

from __future__ import annotations

from uuid import UUID

from shared.db.models import Node
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

_SAMPLE_TERMS = [
    {
        "value": "ephemeral",
        "pos": "adjective",
        "cefr": "C1",
        "meaning": "Lasting for a very short time.",
    },
    {
        "value": "resilient",
        "pos": "adjective",
        "cefr": "B2",
        "meaning": "Able to recover quickly from difficulties; tough.",
    },
    {
        "value": "ubiquitous",
        "pos": "adjective",
        "cefr": "C1",
        "meaning": "Present, appearing, or found everywhere.",
    },
    {
        "value": "candid",
        "pos": "adjective",
        "cefr": "B2",
        "meaning": "Truthful and straightforward; frank.",
    },
    {
        "value": "diligent",
        "pos": "adjective",
        "cefr": "B2",
        "meaning": "Showing care and conscientiousness in work or duties.",
    },
]


async def _user_has_content(session: AsyncSession, user_id: UUID) -> bool:
    """Has the user authored any nodes? Cheaper than counting rows."""
    row = (await session.exec(select(Node.id).where(Node.author_id == user_id).limit(1))).first()
    return row is not None


async def seed_sample(session: AsyncSession, user_id: UUID) -> bool:
    """Idempotently seed a Welcome folder + Starter deck for first-time users.

    Returns True if seeding ran, False if user already has content.
    """
    if await _user_has_content(session, user_id):
        return False

    folder_row = (
        await session.execute(
            text(
                """
                INSERT INTO nodes (author_id, type, parent_node_id, name, description)
                VALUES (:uid, 'FOLDER', NULL, 'Welcome', 'Your first folder')
                ON CONFLICT (author_id, name) WHERE name IN ('Welcome', 'Starter Words')
                  DO NOTHING
                RETURNING id
                """
            ),
            {"uid": user_id},
        )
    ).first()
    if folder_row is None:
        return False
    folder_id = folder_row.id
    await session.execute(
        text("INSERT INTO folder_attributes (node_id) VALUES (:id)"),
        {"id": folder_id},
    )

    deck_row = (
        await session.execute(
            text(
                """
                INSERT INTO nodes (author_id, type, parent_node_id, name, description)
                VALUES (:uid, 'DECK', :pid, 'Starter Words',
                        'Five sample terms to try the learn flow')
                RETURNING id
                """
            ),
            {"uid": user_id, "pid": folder_id},
        )
    ).one()
    deck_id = deck_row.id
    await session.execute(
        text("INSERT INTO deck_attributes (node_id) VALUES (:id)"),
        {"id": deck_id},
    )

    for position, sample in enumerate(_SAMPLE_TERMS):
        term_row = (
            await session.execute(
                text(
                    """
                    INSERT INTO terms (value)
                    VALUES (:v)
                    ON CONFLICT (value) DO UPDATE SET value = EXCLUDED.value
                    RETURNING id
                    """
                ),
                {"v": sample["value"]},
            )
        ).one()
        term_id = term_row.id

        def_row = (
            await session.execute(
                text(
                    """
                    INSERT INTO definitions (
                        term_id, part_of_speech, cefr_level, canonical_meaning
                    )
                    VALUES (:tid, :pos, :cefr, :meaning)
                    ON CONFLICT (term_id) DO UPDATE
                    SET canonical_meaning = EXCLUDED.canonical_meaning
                    RETURNING id
                    """
                ),
                {
                    "tid": term_id,
                    "pos": sample["pos"],
                    "cefr": sample["cefr"],
                    "meaning": sample["meaning"],
                },
            )
        ).one()
        await session.execute(
            text(
                """
                INSERT INTO deck_definitions (deck_id, definition_id, position)
                VALUES (:did, :defid, :pos)
                ON CONFLICT (deck_id, definition_id) DO NOTHING
                """
            ),
            {"did": deck_id, "defid": def_row.id, "pos": position},
        )

    await session.execute(
        text(
            """
            UPDATE deck_attributes SET term_count = :n WHERE node_id = :did
            """
        ),
        {"n": len(_SAMPLE_TERMS), "did": deck_id},
    )
    await session.execute(
        text(
            """
            UPDATE nodes SET definition_count = :n WHERE id = :did
            """
        ),
        {"n": len(_SAMPLE_TERMS), "did": deck_id},
    )
    await session.commit()
    return True
