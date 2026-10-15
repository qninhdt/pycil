from datetime import UTC, datetime, timedelta

import pytest

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.library.access import readable
from pycil.library.models import NodeRole, NodeType
from pycil.library.nodes import create_node, delete_node
from pycil.library.schemas import NodeCreate, SenseSort
from pycil.library.senses import sense_page, sources_page
from pycil.study.enums import LearningState
from pycil.study.models import UserSense
from pycil.vocabulary.enums import PartOfSpeech, Tier
from pycil.vocabulary.models import Definition, Sense
from tests.support.account import account
from tests.support.vocabulary import neutral_word


@pytest.fixture
async def library_content(database):
    config = load_config()
    user, roots = await account(database.sessions)
    word_id, first_id = await neutral_word(database.sessions)
    async with database.sessions() as session, session.begin():
        additional = [
            Sense(word_id=word_id, pos=PartOfSpeech.NOUN, tier=Tier.CORE) for _ in range(2)
        ]
        session.add_all(additional)
        await session.flush()
        for index, sense in enumerate(additional):
            session.add(Definition(sense_id=sense.id, content=f"financial meaning {index}"))
        ids = [first_id, *(sense.id for sense in additional)]
        now = datetime.now(UTC)
        for sense_id in ids[:2]:
            session.add(
                UserSense(
                    user_id=user.id,
                    sense_id=sense_id,
                    stability=1,
                    difficulty=5,
                    elo=config.product.study.mastery.initial_elo,
                    last_exposure_at=now - timedelta(days=2),
                    due_at=now - timedelta(days=1),
                    review_count=1,
                    lapse_count=0,
                )
            )
    async with database.sessions() as session:
        deck = await create_node(
            session, user.id, NodeCreate(type=NodeType.DECK, name="Finance", sense_ids=ids), config
        )
    return user, roots, config, deck, ids


@pytest.mark.parametrize("sort", list(SenseSort))
async def test_tied_sense_seek_returns_each_member_once_and_freezes_cutoff(
    database, library_content, sort
):
    user, _, config, deck, ids = library_content
    async with database.sessions() as session:
        node = await readable(session, deck["id"], user.id, config)
        first = await sense_page(
            session, node, user.id, config, database.sessions, sort=sort, limit=1
        )
    assert first["next_cursor"]
    async with database.sessions() as session:
        node = await readable(session, deck["id"], user.id, config)
        remaining = await sense_page(
            session,
            node,
            user.id,
            config,
            database.sessions,
            first["next_cursor"],
            sort=sort,
            limit=10,
        )
    assert remaining["as_of"] == first["as_of"]
    seen = [item["sense_id"] for item in first["senses"] + remaining["senses"]]
    assert len(seen) == len(set(seen)) == 3 and set(seen) == set(ids)
    assert remaining["next_cursor"] is None
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await sense_page(
                session,
                node,
                user.id,
                config,
                database.sessions,
                first["next_cursor"],
                sort=sort,
                state=LearningState.NEW,
            )
        assert error.value.code == "invalid_cursor"


async def test_sense_filters_apply_before_limit_and_deleted_scope_revokes_old_cursor(
    database, library_content
):
    user, _, config, deck, ids = library_content
    async with database.sessions() as session:
        node = await readable(session, deck["id"], user.id, config)
        fresh = await sense_page(
            session, node, user.id, config, database.sessions, state=LearningState.NEW, limit=1
        )
        assert [item["sense_id"] for item in fresh["senses"]] == [ids[-1]]
        no_literal_match = await sense_page(
            session, node, user.id, config, database.sessions, q="bank%"
        )
        assert no_literal_match["senses"] == []
        first = await sense_page(session, node, user.id, config, database.sessions, limit=1)
    async with database.sessions() as session:
        await delete_node(session, user.id, deck["id"], config)
    async with database.sessions() as session:
        with pytest.raises(Problem) as error:
            await sense_page(
                session, node, user.id, config, database.sessions, first["next_cursor"]
            )
        assert error.value.status == 404


async def test_source_projection_deduplicates_reference_aliases_and_reports_inline_overflow(
    database, library_content
):
    user, roots, config, deck, ids = library_content
    small = config.model_copy(
        update={
            "product": config.product.model_copy(
                update={
                    "projections": config.product.projections.model_copy(
                        update={"inline_sources": 1}
                    )
                }
            )
        }
    )
    async with database.sessions() as session:
        other = await create_node(
            session,
            user.id,
            NodeCreate(type=NodeType.DECK, name="Other", sense_ids=[ids[0]]),
            config,
        )
    async with database.sessions() as session:
        await create_node(
            session,
            user.id,
            NodeCreate(type=NodeType.REFERENCE, name="Alias", reference_id=deck["id"]),
            config,
        )
    scope = roots[NodeRole.PERSONAL_ROOT].id
    async with database.sessions() as session:
        root = await readable(session, scope, user.id, config)
        page = await sense_page(session, root, user.id, small, database.sessions, include="sources")
        item = next(item for item in page["senses"] if item["sense_id"] == ids[0])
        assert item["source_count"] == 2 and item["sources_has_more"] is True
        assert len(item["sources"]) == 1
        source_page = await sources_page(session, scope, ids[0], user.id, config, limit=1)
    async with database.sessions() as session:
        next_page = await sources_page(
            session, scope, ids[0], user.id, config, source_page["next_cursor"]
        )
    assert {entry["id"] for entry in source_page["decks"] + next_page["decks"]} == {
        deck["id"],
        other["id"],
    }
