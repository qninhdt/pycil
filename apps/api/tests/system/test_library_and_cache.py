"""SYS-B — the nested tree, folder study and references, over HTTP.

Three product promises are checked here, and they are the ones a learner would notice
breaking:

- a folder can be studied as a whole, and a word reachable two ways is still one item;
- a reference shares what its owner shared and nothing more;
- revoking a share takes effect on the next read, whatever a cache still holds.

Authorization is the database's decision on every read, so the last point is a
*negative* test: cached metadata may be stale, and access must be denied anyway.
"""

import asyncio

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]


async def test_a_folder_session_gathers_its_whole_subtree_once(actor, corpus, durable):
    """Nested folders, one deck, one word reachable twice — one item, not two.

    The second path is a reference into the same subtree, so the same sense is
    reachable through two routes. A naive gather concatenates the per-deck lists and
    the learner is admitted the same word twice, which produces a second graded item
    for one word in one session.

    The invariant is therefore about *admission and grading*, not about how many times
    a word appears on screen: the design is explicit that a session holds "exactly one
    graded item per admitted sense", while an exposure and a later ungraded re-ask are
    the same sense being taught rather than counted again.
    """
    owner = actor.new()
    sense = corpus["resilient"]

    root = await owner.folder("IELTS")
    nested = await owner.folder("Writing", parent_id=root["id"])
    deck = await owner.deck("Task 1", parent_id=nested["id"])
    await owner.add_sense(deck["id"], sense)

    # A second route to the same deck, inside the same subtree.
    await owner.reference("Task 1 (link)", deck["id"], parent_id=root["id"])

    session = await owner.start_session(root["id"])
    assert session["firstState"] == "ready"
    assert session["admittedCount"] == 1, (
        "a sense reachable by two paths was admitted more than once"
    )

    delivered = await _drain(owner, session["sessionId"])

    assert delivered, "a folder session admitted nothing"
    assert set(delivered) == {sense}, "a folder session delivered something else"
    assert (
        await durable.count(
            "SELECT count(*) FROM responses WHERE session_id = $1", session["sessionId"]
        )
        == 1
    ), "one admitted sense produced more than one graded answer"


async def test_a_folder_reference_contributes_its_whole_subtree(actor, corpus):
    """Sharing a folder shares everything readable inside it, at any depth."""
    owner = actor.new()
    sense = corpus["tenacious"]

    source = await owner.folder("Source")
    inner = await owner.folder("Inner", parent_id=source["id"])
    deep_deck = await owner.deck("Deep", parent_id=inner["id"])
    await owner.add_sense(deep_deck["id"], sense)

    holder = await owner.folder("Holder")
    await owner.reference("shared section", source["id"], parent_id=holder["id"])

    session = await owner.start_session(holder["id"])

    assert session["admittedCount"] == 1, "a folder reference did not reach its subtree"


async def test_a_reference_shares_the_target_and_nothing_beside_it(actor, corpus):
    """A reference into someone else's folder must not become a directory listing.

    B publishes one folder and keeps a private one beside it. A references the
    published folder: A must reach its words and never learn the private one exists.
    """
    owner_b = actor.new()
    sense = corpus["meticulous"]
    shared_folder = await owner_b.folder("Shared", visibility="PUBLIC")
    public_deck = await owner_b.deck("Public deck", parent_id=shared_folder["id"])
    await owner_b.add_sense(public_deck["id"], sense)
    # A sibling, not a child: publishing a folder publishes everything inside it, so
    # a private descendant would be a contradiction rather than a scenario.
    secret = await owner_b.folder("Private notes")

    owner_a = actor.new()
    link = await owner_a.reference("B's folder", shared_folder["id"])

    readable = await owner_a.ok("GET", f"/v1/nodes/{link['id']}")
    assert readable["targetNodeId"] == shared_folder["id"]

    denied = await owner_a.get(f"/v1/nodes/{secret['id']}")
    assert denied.status_code == 404

    items = await owner_a.ok("GET", f"/v1/folders/{shared_folder['id']}/items")
    assert [item["senseId"] for item in items] == [sense]


async def test_a_reference_can_point_at_another_owners_public_deck(actor, corpus):
    """What you can read, you may point at — the two rules must agree.

    A narrower reference rule is how a deck inherited-public through its owner's
    published folder becomes readable but unreferenceable: the caller gets a 404 for
    content they are looking at.
    """
    owner_b = actor.new()
    sense = corpus["pragmatic"]
    folder = await owner_b.folder("Shared", visibility="PUBLIC")
    deck = await owner_b.deck("Deck", parent_id=folder["id"])
    await owner_b.add_sense(deck["id"], sense)

    owner_a = actor.new()
    link = await owner_a.reference("B's deck", deck["id"])

    assert link["targetNodeId"] == deck["id"]
    assert await owner_a.deck_sense_ids(deck["id"]) == [sense]


async def test_a_reference_to_a_private_target_is_refused(actor):
    """Pointing at something unreadable is refused at creation, not at render."""
    owner_b = actor.new()
    private_deck = await owner_b.deck("Private deck")

    owner_a = actor.new()
    response = await owner_a.post(
        "/v1/nodes",
        json={"type": "REFERENCE", "name": "nope", "targetNodeId": private_deck["id"]},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "reference_target_not_found"


async def test_revoking_a_share_denies_the_next_read(actor, corpus):
    """The cache may still hold old metadata; authorization is the database's.

    This is the failure mode a shared cache introduces: the entry was written when the
    folder was public and nothing evicts it. If authorization consulted the cache, the
    deck would stay readable after the owner changed their mind.
    """
    owner_b = actor.new()
    sense = corpus["elusive"]
    folder = await owner_b.folder("Shared", visibility="PUBLIC")
    deck = await owner_b.deck("Deck", parent_id=folder["id"])
    await owner_b.add_sense(deck["id"], sense)

    reader = actor.new()
    link = await reader.reference("link", deck["id"])
    # Read through the reference while it is shared, so any cache is warm.
    assert (await reader.get(f"/v1/decks/{deck['id']}/items")).status_code == 200

    await owner_b.status(
        "PATCH", f"/v1/nodes/{folder['id']}/visibility", 200, json={"visibility": "PRIVATE"}
    )

    revoked = await reader.get(f"/v1/decks/{deck['id']}/items")
    assert revoked.status_code == 404, "a revoked share was still readable"

    # The reference node itself stays, and stays readable: it is the reader's own
    # node, and its whole purpose is to say the target went away rather than to
    # silently render as an empty deck.
    assert (await reader.get(f"/v1/nodes/{link['id']}")).status_code == 200
    assert (await reader.get(f"/v1/nodes/{deck['id']}")).status_code == 404


async def test_a_public_ancestor_grants_read_but_never_write(actor):
    """Inherited visibility is a read grant. Writing stays with the owner."""
    owner = actor.new()
    folder = await owner.folder("Shared", visibility="PUBLIC")
    deck = await owner.deck("Deck", parent_id=folder["id"])

    stranger = actor.new()
    assert (await stranger.get(f"/v1/nodes/{deck['id']}")).status_code == 200

    for method, path, body in (
        ("PATCH", f"/v1/nodes/{deck['id']}", {"name": "renamed"}),
        ("PATCH", f"/v1/nodes/{deck['id']}/visibility", {"visibility": "PUBLIC"}),
        ("PATCH", f"/v1/nodes/{deck['id']}/move", {"parentNodeId": None}),
        ("POST", f"/v1/decks/{deck['id']}/senses", {"senseId": 1}),
    ):
        response = await stranger._client.request(method, path, headers=stranger.headers, json=body)
        assert response.status_code in {403, 404}, f"{method} {path} -> {response.status_code}"


async def test_a_move_that_would_create_a_cycle_is_refused(actor):
    """A cycle is a bounded domain error, not a stack overflow or a silent no-op."""
    owner = actor.new()
    outer = await owner.folder("Outer")
    inner = await owner.folder("Inner", parent_id=outer["id"])

    response = await owner.patch(
        f"/v1/nodes/{outer['id']}/move", json={"parentNodeId": inner["id"]}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "node_move_would_create_cycle"


async def test_mutually_referencing_folders_terminate(actor, corpus):
    """Two folders referencing each other must not walk forever.

    A reference to a folder expands to that folder's subtree, which may contain a
    reference back. Without a visited set the walk alternates indefinitely.
    """
    owner = actor.new()
    sense = corpus["vivid"]
    left = await owner.folder("Left")
    right = await owner.folder("Right")
    deck = await owner.deck("Deck", parent_id=left["id"])
    await owner.add_sense(deck["id"], sense)

    await owner.reference("L to R", right["id"], parent_id=left["id"])
    await owner.reference("R to L", left["id"], parent_id=right["id"])

    items = await asyncio.wait_for(owner.ok("GET", f"/v1/folders/{left['id']}/items"), timeout=30)

    assert [item["senseId"] for item in items] == [sense]


async def test_a_folder_cannot_be_made_public_without_confirmation(actor):
    """Publishing a folder publishes its subtree, so it takes an explicit acknowledgement."""
    owner = actor.new()
    folder = await owner.folder("Private")
    await owner.deck("Hidden deck", parent_id=folder["id"])

    refused = await owner.patch(
        f"/v1/nodes/{folder['id']}/visibility", json={"visibility": "PUBLIC"}
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "folder_publication_requires_confirmation"

    allowed = await owner.patch(
        f"/v1/nodes/{folder['id']}/visibility",
        json={"visibility": "PUBLIC", "confirmSubtreePublication": True},
    )
    assert allowed.status_code == 200
    assert allowed.json()["visibility"] == "PUBLIC"


# --- helpers ------------------------------------------------------------------


async def _drain(caller, session_id: str, *, limit: int = 40) -> list[int]:
    """Answer or dismiss every item the session offers, collecting the sense ids."""
    delivered: list[int] = []
    for _ in range(limit):
        state = await caller.next_question(session_id)
        if state["state"] == "exhausted":
            return delivered
        if state["state"] == "preparing":
            await asyncio.sleep(0.5)
            continue
        if state["state"] == "break":
            continue
        delivered.append(state["senseId"])
        if state["questionId"] is None:
            # Exposure: shown, not answered. The next call moves on.
            continue
        await caller.answer(session_id, state["questionId"], "run")
    return delivered
