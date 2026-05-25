"""Deep-clone a deck into the cloner's tree.

Deep-copies terms, definitions, paraphrases, examples, and questions.
NOT cloned: responses, user_term_stats (those are personal). Records
attribution in `deck_clones`. Runs in a single transaction; <2s on a
1000-term deck per phase 9 plan.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def deep_clone(
    session: AsyncSession,
    *,
    user_id: UUID,
    source_deck_id: UUID,
    parent_node_id: UUID | None = None,
) -> UUID:
    """Clone a deck. Returns the new deck's node id."""
    src = (
        await session.execute(
            text(
                "SELECT id, name, description FROM nodes "
                "WHERE id = :id AND type = 'DECK' AND visibility = 'PUBLIC'"
            ),
            {"id": source_deck_id},
        )
    ).first()
    if src is None:
        raise LookupError("source_deck_not_found_or_not_public")

    new_deck = (
        await session.execute(
            text(
                """
                INSERT INTO nodes (author_id, type, parent_node_id, name, description, visibility)
                VALUES (:uid, 'DECK', :pid, :name, :desc, 'PRIVATE')
                RETURNING id
                """
            ),
            {
                "uid": user_id,
                "pid": parent_node_id,
                "name": f"{src.name} (Copy)",
                "desc": src.description,
            },
        )
    ).one()
    new_deck_id = new_deck.id

    await session.execute(
        text(
            "INSERT INTO deck_attributes (node_id, settings) "
            "SELECT :nid, settings FROM deck_attributes WHERE node_id = :src"
        ),
        {"nid": new_deck_id, "src": source_deck_id},
    )

    # Deep-copy each (term, definition, paraphrases, examples, questions).
    # Insert NEW terms (or reuse if value already exists for cloner — terms.value is unique),
    # NEW definitions, NEW paraphrases/examples/questions, and link via deck_definitions.
    src_defs = (
        await session.execute(
            text(
                """
                SELECT dd.position, d.id AS def_id, d.term_id, d.cefr_level::text AS cefr,
                       d.part_of_speech::text AS pos, d.synonyms, d.antonyms, d.hyponyms,
                       d.hypernyms, d.meronyms, d.holonyms, d.homophones, d.notes,
                       d.tags, d.canonical_meaning, d.translation, d.tts_url,
                       t.value AS term_value, t.type::text AS term_type
                  FROM deck_definitions dd
                  JOIN definitions d ON d.id = dd.definition_id
                  JOIN terms t ON t.id = d.term_id
                 WHERE dd.deck_id = :src
                 ORDER BY dd.position
                """
            ),
            {"src": source_deck_id},
        )
    ).all()

    for src_def in src_defs:
        # Reuse existing term row keyed on UNIQUE(value); INSERT-ON-CONFLICT.
        new_term = (
            await session.execute(
                text(
                    """
                    INSERT INTO terms (value, type)
                    VALUES (:val, CAST(:t AS term_type))
                    ON CONFLICT (value) DO UPDATE SET updated_at = NOW()
                    RETURNING id
                    """
                ),
                {"val": src_def.term_value, "t": src_def.term_type},
            )
        ).one()

        new_def = (
            await session.execute(
                text(
                    """
                    INSERT INTO definitions (
                        term_id, cefr_level, part_of_speech,
                        synonyms, antonyms, hyponyms, hypernyms, meronyms, holonyms,
                        homophones, notes, tags, canonical_meaning, translation, tts_url
                    )
                    VALUES (
                        :tid, :cefr::cefr_level, :pos::part_of_speech,
                        :syn, :ant, :hypo, :hyper, :mero, :holo,
                        :homo, :notes, :tags, :canon, CAST(:trans AS jsonb), CAST(:tts AS jsonb)
                    )
                    ON CONFLICT (term_id) DO UPDATE
                      SET canonical_meaning = EXCLUDED.canonical_meaning,
                          updated_at = NOW()
                    RETURNING id
                    """
                ),
                {
                    "tid": new_term.id,
                    "cefr": src_def.cefr,
                    "pos": src_def.pos,
                    "syn": src_def.synonyms or [],
                    "ant": src_def.antonyms or [],
                    "hypo": src_def.hyponyms or [],
                    "hyper": src_def.hypernyms or [],
                    "mero": src_def.meronyms or [],
                    "holo": src_def.holonyms or [],
                    "homo": src_def.homophones or [],
                    "notes": src_def.notes or [],
                    "tags": src_def.tags or [],
                    "canon": src_def.canonical_meaning,
                    "trans": "{}",
                    "tts": "{}",
                },
            )
        ).one()

        await session.execute(
            text(
                "INSERT INTO definition_paraphrases (definition_id, value, cefr_level) "
                "SELECT :nid, value, cefr_level FROM definition_paraphrases "
                "WHERE definition_id = :sid"
            ),
            {"nid": new_def.id, "sid": src_def.def_id},
        )
        await session.execute(
            text(
                "INSERT INTO term_example_sentences (definition_id, value, cefr_level) "
                "SELECT :nid, value, cefr_level FROM term_example_sentences "
                "WHERE definition_id = :sid"
            ),
            {"nid": new_def.id, "sid": src_def.def_id},
        )
        await session.execute(
            text(
                """
                INSERT INTO questions (definition_id, type, data, elo, variant_seed)
                SELECT :nid, type, data, elo, variant_seed
                  FROM questions
                 WHERE definition_id = :sid
                """
            ),
            {"nid": new_def.id, "sid": src_def.def_id},
        )

        await session.execute(
            text(
                """
                INSERT INTO deck_definitions (deck_id, definition_id, position)
                VALUES (:nid, :did, :pos)
                """
            ),
            {"nid": new_deck_id, "did": new_def.id, "pos": src_def.position},
        )

    await session.execute(
        text(
            """
            INSERT INTO deck_clones (source_deck_id, cloned_deck_id, cloned_by_user)
            VALUES (:src, :new, :uid)
            """
        ),
        {"src": source_deck_id, "new": new_deck_id, "uid": user_id},
    )
    await session.commit()
    return new_deck_id
