"""Authorization matrix for ``GET /v1/senses/{senseId}``.

A sense is not an owned pycil resource; it is Lexi content made reachable by deck
membership. Access is therefore derived from the decks holding it, and every way
that derivation can over-grant is pinned here:

- soft-deleted deck (``delete_node`` is a soft delete)
- deck under a deleted ancestor (a revoked share)
- inherited-public through a same-owner public folder (must still GRANT)
- visibility revoked on the public ancestor
- ANONYMOUS caller against a private deck, which a ``viewer_id IS NULL``
  short-circuit in the SQL predicate used to allow

Unknown, unreferenced and unreadable all collapse to one 404 with one code so the
endpoint is not a membership oracle.
"""

import uuid
from types import SimpleNamespace

import pytest

from pycil.auth.models import User
from pycil.auth.schemas import CurrentUser
from pycil.common.errors import NotFoundError
from pycil.content import service as content_service
from pycil.content.router import sense_detail
from pycil.hierarchy import service as hierarchy_service
from pycil.hierarchy.models import NodeType, Visibility

pytestmark = pytest.mark.asyncio

_KNOWN_SENSE = 9001
_MISSING_IN_LEXI = 9999


class FakeLexiReader:
    """Returns a full sense view for known ids only, so 'absent in Lexi' is real."""

    def __init__(self, known: dict[int, str] | None = None):
        self.known = known or {_KNOWN_SENSE: "eloquent"}
        self.calls: list[list[int]] = []

    async def get_senses(self, sense_ids):
        self.calls.append(list(sense_ids))
        return [
            SimpleNamespace(
                definition="fluent and persuasive in speech",
                tier="core",
                pos="adjective",
                cefr_level="C1",
                sense_id=sid,
                examples=["She gave an eloquent speech."],
                word=self.known[sid],
                word_id=42,
                ipa_uk="ˈel.ə.kwənt",
                ipa_us="ˈel.ə.kwənt",
                guideword="SPEAKING WELL",
                grammar=["[before noun]"],
                register="formal",
                connotation="positive",
                collocations=["an eloquent speech"],
                domain=None,
                usage_note=None,
                forms=[SimpleNamespace(inf="comparative", surface="more eloquent")],
                references=[SimpleNamespace(source="cambridge", source_ref="eloquent-1")],
                relations=[
                    SimpleNamespace(
                        rel_type="synonym",
                        to_word_display="articulate",
                        to_word_id=43,
                        to_word_status="done",
                        wsd_state="pending",
                        to_sense_id=None,
                        to_sense_gloss=None,
                    )
                ],
            )
            for sid in sense_ids
            if sid in self.known
        ]


async def _user(session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _cu(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email)


async def _deck_with_sense(session, author_id, *, name, parent_node_id=None, visibility=None):
    deck = await hierarchy_service.create_node(
        session,
        author_id,
        node_type=NodeType.DECK,
        name=name,
        parent_node_id=parent_node_id,
        **({"visibility": visibility} if visibility is not None else {}),
    )
    await content_service.add_sense(session, deck.id, _KNOWN_SENSE)
    return deck


async def _public_folder(session, author_id, name, parent_node_id=None):
    return await hierarchy_service.create_node(
        session,
        author_id,
        node_type=NodeType.FOLDER,
        name=name,
        parent_node_id=parent_node_id,
        visibility=Visibility.PUBLIC,
        confirm_subtree_publication=True,
    )


# --- grants ----------------------------------------------------------------


async def test_owner_reads_a_sense_in_their_own_private_deck(session):
    owner = await _user(session, "sd-owner@example.com")
    await _deck_with_sense(session, owner.id, name="my deck")

    read = await sense_detail(_KNOWN_SENSE, _cu(owner), session, FakeLexiReader())

    assert read.sense_id == _KNOWN_SENSE
    assert read.word == "eloquent"
    assert read.word_id == 42
    # The full record, which the listing DTO deliberately does not carry.
    assert read.ipa_uk == "ˈel.ə.kwənt"
    assert read.guideword == "SPEAKING WELL"
    assert [f.surface for f in read.forms] == ["more eloquent"]
    assert [r.source_ref for r in read.references] == ["eloquent-1"]
    assert [r.to_word_display for r in read.relations] == ["articulate"]


async def test_anonymous_reads_a_sense_in_a_public_deck(session):
    owner = await _user(session, "sd-public@example.com")
    await _deck_with_sense(
        session, owner.id, name="public deck", visibility=Visibility.PUBLIC
    )

    read = await sense_detail(_KNOWN_SENSE, None, session, FakeLexiReader())

    assert read.sense_id == _KNOWN_SENSE
    assert read.word == "eloquent"


async def test_private_deck_under_a_same_owner_public_folder_is_readable(session):
    # Inherited public MUST still grant, or publishing a folder publishes nothing.
    owner = await _user(session, "sd-inherit-owner@example.com")
    reader = await _user(session, "sd-inherit-reader@example.com")
    folder = await _public_folder(session, owner.id, "published folder")
    await _deck_with_sense(session, owner.id, name="inherited deck", parent_node_id=folder.id)

    read = await sense_detail(_KNOWN_SENSE, _cu(reader), session, FakeLexiReader())
    assert read.sense_id == _KNOWN_SENSE

    anon = await sense_detail(_KNOWN_SENSE, None, session, FakeLexiReader())
    assert anon.sense_id == _KNOWN_SENSE


# --- denials ---------------------------------------------------------------


async def test_signed_in_user_cannot_read_someone_elses_private_deck(session):
    owner = await _user(session, "sd-priv-owner@example.com")
    stranger = await _user(session, "sd-priv-stranger@example.com")
    await _deck_with_sense(session, owner.id, name="private deck")

    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(_KNOWN_SENSE, _cu(stranger), session, FakeLexiReader())


async def test_anonymous_cannot_read_a_private_deck(session):
    # The bypass this phase closed: the readable-deck predicate short-circuited to
    # TRUE for a NULL viewer_id, so signing OUT granted strictly more access than
    # signing in. Anonymous must land on exactly the public / inherited-public
    # paths, nothing more.
    owner = await _user(session, "sd-anon-owner@example.com")
    await _deck_with_sense(session, owner.id, name="private deck")

    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(_KNOWN_SENSE, None, session, FakeLexiReader())


async def test_sense_in_no_deck_at_all_is_not_found(session):
    owner = await _user(session, "sd-orphan@example.com")
    # A deck exists and is readable, but holds a DIFFERENT sense.
    deck = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="unrelated deck"
    )
    await content_service.add_sense(session, deck.id, 1234)

    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(_KNOWN_SENSE, _cu(owner), session, FakeLexiReader())


async def test_sense_absent_from_lexi_is_not_found(session):
    # Membership without content: same 404, same code, so the caller cannot tell
    # "not yours" from "does not exist".
    owner = await _user(session, "sd-nolexi@example.com")
    deck = await hierarchy_service.create_node(
        session, owner.id, node_type=NodeType.DECK, name="deck"
    )
    await content_service.add_sense(session, deck.id, _MISSING_IN_LEXI)

    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(_MISSING_IN_LEXI, _cu(owner), session, FakeLexiReader())


async def test_soft_deleted_deck_stops_granting_access(session):
    # delete_node is a SOFT delete. Without the live-chain clause the sense would
    # stay world-readable through a deck the owner believes they deleted.
    owner = await _user(session, "sd-deleted-owner@example.com")
    deck = await _deck_with_sense(
        session, owner.id, name="public then deleted", visibility=Visibility.PUBLIC
    )
    reader = await _user(session, "sd-deleted-reader@example.com")
    assert (await sense_detail(_KNOWN_SENSE, _cu(reader), session, FakeLexiReader())).sense_id

    await hierarchy_service.soft_delete_node(session, deck)

    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(_KNOWN_SENSE, _cu(reader), session, FakeLexiReader())
    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(_KNOWN_SENSE, None, session, FakeLexiReader())


async def test_deleted_ancestor_folder_revokes_an_inherited_public_deck(session):
    owner = await _user(session, "sd-delanc-owner@example.com")
    reader = await _user(session, "sd-delanc-reader@example.com")
    folder = await _public_folder(session, owner.id, "published folder")
    await _deck_with_sense(session, owner.id, name="inherited deck", parent_node_id=folder.id)
    assert (await sense_detail(_KNOWN_SENSE, _cu(reader), session, FakeLexiReader())).sense_id

    await hierarchy_service.soft_delete_node(session, folder)

    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(_KNOWN_SENSE, _cu(reader), session, FakeLexiReader())


async def test_revoking_the_public_ancestor_revokes_the_sense(session):
    # The reference-revocation shape, seen from the sense endpoint: a REFERENCE
    # never grants more than the target deck grants on its own, so hiding the
    # target's public ancestor is what revokes access.
    owner = await _user(session, "sd-revoke-owner@example.com")
    reader = await _user(session, "sd-revoke-reader@example.com")
    folder = await _public_folder(session, owner.id, "published folder")
    await _deck_with_sense(session, owner.id, name="inherited deck", parent_node_id=folder.id)
    reference_root = await _public_folder(session, owner.id, "reference root")
    await hierarchy_service.create_node(
        session,
        owner.id,
        node_type=NodeType.REFERENCE,
        name="external reference",
        parent_node_id=reference_root.id,
        target_node_id=(
            await content_service.deck_ids_for_sense(session, _KNOWN_SENSE)
        )[0],
    )
    assert (await sense_detail(_KNOWN_SENSE, _cu(reader), session, FakeLexiReader())).sense_id

    await hierarchy_service.set_visibility(session, folder, Visibility.PRIVATE)

    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(_KNOWN_SENSE, _cu(reader), session, FakeLexiReader())


async def test_unknown_sense_id_shape_is_the_same_404(session):
    owner = await _user(session, "sd-unknown@example.com")
    await _deck_with_sense(session, owner.id, name="deck")

    with pytest.raises(NotFoundError, match="sense_not_found"):
        await sense_detail(uuid.uuid4().int % 100000, _cu(owner), session, FakeLexiReader())
