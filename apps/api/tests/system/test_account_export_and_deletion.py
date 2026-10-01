"""SYS-L — account export and the deletion failure boundary.

Export and deletion are the two operations where a mistake is unrecoverable for the
learner, so both are checked for what they *exclude* as much as what they include.

- **Export** must carry one learner's own rows and no one else's, and it must not
  become a copy of the shared dictionary: the words are the commons every learner
  studies, not personal data, and shipping them would make one learner's export a dump
  of the product's content.
- **Deletion** is ordered so a failure cannot strand a learner in a half-deleted state.
  Clerk is the sign-in authority, so the external subject goes first; while it exists, a
  sign-in would just-in-time provision a fresh empty account and the learner would
  appear resurrected. This journey exercises the failure the ordering exists to prevent,
  by deleting with no Clerk credential configured at all.
"""

import pytest

from tests.system.conftest import requires_stack

pytestmark = [pytest.mark.asyncio, requires_stack]


async def test_an_export_contains_only_the_callers_own_data(actor):
    """Two learners' accounts, one export: the other's rows are absent.

    The failure this catches is a query that filters by the wrong column or forgets a
    filter entirely, which looks correct against a single account and leaks every
    account in production.
    """
    owner = actor.new()
    mine = await owner.deck("Mine")
    await owner.ok("POST", "/v1/nodes", json={"type": "DECK", "name": "Also mine"})

    stranger = actor.new()
    theirs = await stranger.deck("Theirs")
    await stranger.ok("POST", "/v1/nodes", json={"type": "DECK", "name": "Also theirs"})

    export = await owner.ok("GET", "/v1/me/export")

    names = [node["name"] for node in export["collection"]]
    ids = [str(node["id"]) for node in export["collection"]]

    assert "Mine" in names and "Also mine" in names, names
    assert "Theirs" not in names and "Also theirs" not in names, names
    assert theirs["id"] not in ids, "another learner's node appeared in the export"
    assert mine["id"] in ids, ids


async def test_an_export_does_not_carry_the_shared_dictionary(actor, corpus):
    """A deck's sense ids are the learner's; the words behind them are not.

    The dictionary is shared content every learner studies. An export that carried the
    definitions would be a copy of the product's own corpus attached to one account —
    and would grow without bound as the corpus does.
    """
    owner = actor.new()
    sense = corpus["resilient"]
    deck = await owner.deck("Studied")
    await owner.add_sense(deck["id"], sense)

    export = await owner.ok("GET", "/v1/me/export")

    serialized = str(export)
    assert str(sense) in serialized, "the learner's own membership was not exported"
    # The generated definition is what the dictionary holds; it belongs to Lexi, not
    # to this account, so it must not appear anywhere in the export.
    assert "definition of" not in serialized, "the export carried shared dictionary content"


async def test_deletion_requires_an_explicit_confirmation(actor, durable):
    """A delete without the confirmation word is refused and changes nothing."""
    caller = actor.new()
    await caller.deck("Kept")
    me = await caller.me()

    refused = await caller.delete("/v1/me", json={"confirmation": "wrong"})

    assert refused.status_code == 401, refused.text
    assert await durable.count("SELECT count(*) FROM users WHERE id = $1", me["id"]) == 1


async def test_a_deletion_that_cannot_reach_the_sign_in_authority_leaves_the_account_intact(
    actor, durable
):
    """The ordering guarantee: refuse rather than half-delete.

    The stack runs without a Clerk management credential, so the external subject
    cannot be removed. Deleting the local rows anyway would be the worse failure —
    the subject would still exist, and the next sign-in would provision a fresh empty
    account while the learner's real data sat unreachable behind a dead UUID.

    So the correct behaviour is a refusal with nothing removed. The account, its nodes
    and its schedule all survive, and a later retry with a credential can finish.
    """
    caller = actor.new()
    me = await caller.me()
    deck = await caller.deck("Kept")

    response = await caller.delete("/v1/me", json={"confirmation": "DELETE"})

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "clerk_not_configured"

    assert await durable.count("SELECT count(*) FROM users WHERE id = $1", me["id"]) == 1, (
        "a refused deletion removed the account anyway"
    )
    assert (
        await durable.count(
            "SELECT count(*) FROM nodes WHERE id = $1 AND deleted_at IS NULL", deck["id"]
        )
        == 1
    ), "a refused deletion removed the learner's data anyway"


async def test_a_refused_deletion_is_repeatable(actor, durable):
    """A retry converges: the same refusal, and still nothing removed.

    Deletion is meant to be idempotent, and the refused case is where that is easiest
    to get wrong — a first attempt that removed some rows and then failed would make
    the second attempt behave differently from the first.
    """
    caller = actor.new()
    me = await caller.me()
    await caller.deck("Kept")

    first = await caller.delete("/v1/me", json={"confirmation": "DELETE"})
    second = await caller.delete("/v1/me", json={"confirmation": "DELETE"})

    assert first.status_code == second.status_code == 503
    assert first.json()["code"] == second.json()["code"]
    assert await durable.count("SELECT count(*) FROM users WHERE id = $1", me["id"]) == 1


async def test_an_export_is_not_readable_without_a_credential(actor):
    """The export is the most sensitive read in the product, so it is never anonymous."""
    response = await actor.anonymous().get("/v1/me/export")

    assert response.status_code == 401
