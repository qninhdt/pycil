from types import SimpleNamespace

import pytest
from sqlalchemy import select

from pycil.vocabulary.enums import (
    GenerationState,
    PartOfSpeech,
    ResolutionState,
    SenseRelationType,
    Tier,
)
from pycil.vocabulary.models import Definition, Sense, SenseRelation, Word
from pycil.vocabulary.relations.resolve import resolve_relations
from tests.support.vocabulary import neutral_word


class RelationDecision:
    def __init__(self, edit=None):
        self.edit = edit

    async def decide(self, schema, context):
        assert context["relation"]["rule"]
        if self.edit is not None:
            await self.edit()
        return schema(matched_sense="candidate_1")


async def relation_data(sessions):
    word_id, source_id = await neutral_word(sessions)
    async with sessions() as session, session.begin():
        target = Word(lemma="lender", match_key="lender", generation_state=GenerationState.DONE)
        deferred = Word(lemma="creditor", match_key="creditor")
        session.add_all([target, deferred])
        await session.flush()
        sense = Sense(word_id=target.id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(sense)
        await session.flush()
        definition = Definition(
            sense_id=sense.id, theme_id=None, content="an institution that lends money"
        )
        session.add(definition)
        session.add(
            SenseRelation(
                from_sense_id=source_id, to_word_id=deferred.id, rel_type=SenseRelationType.SYNONYM
            )
        )
        edge = SenseRelation(
            from_sense_id=source_id, to_word_id=target.id, rel_type=SenseRelationType.HYPERNYM
        )
        session.add(edge)
        await session.flush()
        return edge.id, sense.id, definition.id


async def test_relation_resolves_ready_target_and_neutral_edit_invalidates_evidence(database):
    edge_id, target_id, definition_id = await relation_data(database.sessions)
    outcomes = await resolve_relations(database.sessions, RelationDecision(), batch_size=1)
    assert [(item.edge_id, item.state) for item in outcomes] == [
        (edge_id, ResolutionState.RESOLVED)
    ]
    async with database.sessions() as session, session.begin():
        edge = await session.get(SenseRelation, edge_id)
        assert edge.to_sense_id == target_id
        assert edge.target_hash is not None
        definition = await session.get(Definition, definition_id)
        definition.content = "a person who lends money"
    async with database.sessions() as session:
        edge = await session.get(SenseRelation, edge_id)
        assert edge.to_sense_id is None
        assert edge.target_hash is None
        assert edge.resolve_attempted_at is None


@pytest.mark.parametrize("choice", ["no_candidate", "outside_inventory"])
async def test_relation_no_match_is_recorded_but_invalid_choice_remains_retryable(database, choice):
    edge_id, _, _ = await relation_data(database.sessions)

    class Decision:
        async def decide(self, *args, **options):
            return SimpleNamespace(matched_sense=choice)

    result = await resolve_relations(database.sessions, Decision())
    expected = ResolutionState.UNRESOLVABLE if choice == "no_candidate" else ResolutionState.ERROR
    assert [(item.edge_id, item.state) for item in result] == [(edge_id, expected)]
    async with database.sessions() as session:
        edge = await session.get(SenseRelation, edge_id)
        assert edge.to_sense_id is None and edge.target_hash is None
        assert (edge.resolve_attempted_at is not None) == (choice == "no_candidate")


async def test_ready_target_without_matching_pos_is_unresolvable_without_inference(database):
    edge_id, target_id, _ = await relation_data(database.sessions)
    async with database.sessions() as session, session.begin():
        (await session.get(Sense, target_id)).pos = PartOfSpeech.VERB

    class Decision:
        async def decide(self, *args, **options):
            pytest.fail("empty candidate inventory must not invoke a provider")

    result = await resolve_relations(database.sessions, Decision())
    assert [(item.edge_id, item.state) for item in result] == [
        (edge_id, ResolutionState.UNRESOLVABLE)
    ]
    async with database.sessions() as session:
        edge = await session.get(SenseRelation, edge_id)
        assert edge.to_sense_id is None and edge.resolve_attempted_at is not None


async def test_source_changed_during_inference_prevents_stale_resolution(database):
    edge_id, _, _ = await relation_data(database.sessions)

    async def edit():
        async with database.sessions() as session, session.begin():
            source_id = (await session.get(SenseRelation, edge_id)).from_sense_id
            definition = await session.scalar(
                select(Definition).where(
                    Definition.sense_id == source_id, Definition.theme_id.is_(None)
                )
            )
            definition.content = "new source evidence"

    result = await resolve_relations(database.sessions, RelationDecision(edit))
    assert [(item.edge_id, item.state) for item in result] == [(edge_id, ResolutionState.NOOP)]
    async with database.sessions() as session:
        edge = await session.get(SenseRelation, edge_id)
        assert edge.to_sense_id is None and edge.resolve_attempted_at is None


async def test_relation_does_not_publish_decision_against_changed_inventory(database):
    edge_id, _target_id, definition_id = await relation_data(database.sessions)

    async def edit():
        async with database.sessions() as session, session.begin():
            definition = await session.get(Definition, definition_id)
            definition.content = "a different neutral meaning"

    outcomes = await resolve_relations(database.sessions, RelationDecision(edit))
    assert [(item.edge_id, item.state) for item in outcomes] == [(edge_id, ResolutionState.NOOP)]
    async with database.sessions() as session:
        edge = await session.scalar(select(SenseRelation).where(SenseRelation.id == edge_id))
        assert edge.to_sense_id is None
        assert edge.resolve_attempted_at is None
