"""The api↔worker dispatch contract round-trips through the worker's own decoder.

Producers in the API serialize a dispatch; the worker parses it back with
``from_dispatch``. Both ends must agree on the field names and on the JSON-safe
shape, because the payload crosses a process and a serializer in between. These
assert the values the worker actually receives, not a copy of the producer's
dict.
"""

import json

from pycil.queue.contracts import (
    TASK_KIND_QUESTION_SUPPLY,
    TASK_KIND_WORD,
    SupplyDispatch,
    WordDispatch,
)


def test_word_dispatch_survives_json_round_trip():
    dispatch = WordDispatch(query="serendipity", owner_id="owner-1")
    restored = WordDispatch.from_dispatch(dispatch.to_dispatch())
    assert restored == dispatch


def test_supply_dispatch_normalizes_demands_to_json_safe_lists():
    """Producers hold tuples; the wire holds lists. The worker parses the wire form.

    ``to_dispatch`` is the only writer of the payload, so the invariant is that
    what it emits survives a JSON round trip and parses back to the same values
    the worker reads. Tuples normalize to lists on the way out and stay lists on
    the way in, which is what the stored row actually contains.
    """
    dispatch = SupplyDispatch(
        owner_id="owner-1",
        session_id="session-9",
        round_index=2,
        demands=[(41, 1), (42, 2)],
    )
    wire = json.loads(json.dumps(dispatch.to_dispatch()))
    assert wire["demands"] == [[41, 1], [42, 2]]

    restored = SupplyDispatch.from_dispatch(wire)
    assert restored.owner_id == "owner-1"
    assert restored.session_id == "session-9"
    assert restored.round_index == 2
    assert [list(demand) for demand in restored.demands] == [[41, 1], [42, 2]]


def test_task_kinds_are_stable_wire_values():
    assert TASK_KIND_WORD == "word"
    assert TASK_KIND_QUESTION_SUPPLY == "question_supply"
