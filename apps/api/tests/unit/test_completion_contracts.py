from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pycil.account.schemas import PreferencesPatch, ProfilePatch
from pycil.http import Problem
from pycil.pagination import decode, encode
from pycil.study.progress import streaks, window
from pycil.study.reviews import request_hash
from pycil.study.schemas import Prepare, ReviewBatch, SummaryBatch
from pycil.vocabulary.context import SenseIDs, WordIDs


@pytest.mark.parametrize(
    "body",
    [
        {"sense_id": 1, "rating": "GOOD"},
        {"results": []},
        {"results": [{"sense_id": True, "rating": "GOOD"}]},
        {"results": [{"sense_id": "1", "rating": "GOOD"}]},
        {"results": [{"sense_id": 0, "rating": "GOOD"}]},
        {"results": [{"sense_id": 1, "rating": "CORRECT"}]},
        {"results": [{"sense_id": 1, "rating": "GOOD", "node_id": "x"}]},
        {"results": [{"sense_id": 1, "rating": "GOOD"}] * 2},
        {"results": [{"sense_id": i, "rating": "GOOD"} for i in range(1, 102)]},
    ],
)
def test_strict_batch(body):
    with pytest.raises(ValidationError):
        ReviewBatch.model_validate(body)


def test_batch_hash_is_canonical_and_ordered():
    a = ReviewBatch.model_validate(
        {"results": [{"sense_id": 1, "rating": "GOOD"}, {"sense_id": 2, "rating": "AGAIN"}]}
    )
    b = ReviewBatch.model_validate(
        {"results": [{"rating": "GOOD", "sense_id": 1}, {"rating": "AGAIN", "sense_id": 2}]}
    )
    assert request_hash(a) == request_hash(b)
    assert request_hash(a) != request_hash(ReviewBatch(results=list(reversed(a.results))))
    assert (
        len(ReviewBatch(results=[{"sense_id": i, "rating": "GOOD"} for i in range(1, 101)]).results)
        == 100
    )


@pytest.mark.parametrize(
    "model, body",
    [
        (Prepare, {"node_id": str(uuid4()), "selection": "NOT_YET_DUE"}),
        (Prepare, {"node_id": str(uuid4()), "max_sense_count": True}),
        (PreferencesPatch, {"learning": {"question_budget": 30}}),
        (SummaryBatch, {"node_ids": [str(uuid4())] * 2}),
        (WordIDs, {"word_ids": [1] * 2}),
        (WordIDs, {"word_ids": list(range(1, 32))}),
        (SenseIDs, {"sense_ids": [True]}),
        (SenseIDs, {"sense_ids": list(range(1, 102))}),
        (ProfilePatch, {"handle": None}),
        (ProfilePatch, {"handle": "ab"}),
        (ProfilePatch, {"handle": "éabc"}),
        (ProfilePatch, {"handle": "Kabc"}),
        (ProfilePatch, {"handle": "a" * 31}),
        (ProfilePatch, {"handle": "1abc"}),
        (ProfilePatch, {"bio": "x" * 501}),
        (ProfilePatch, {"country": "VN"}),
        (ProfilePatch, {"plan": "PRO"}),
    ],
)
def test_strict_completion_requests(model, body):
    with pytest.raises(ValidationError):
        model.model_validate(body)


def test_profile_normalization_and_omission():
    assert ProfilePatch(handle="  NiNh_123 ", bio=" Hello ").model_dump() == {
        "handle": "ninh_123",
        "bio": "Hello",
    }
    assert ProfilePatch(bio=None).model_dump(exclude_unset=True) == {"bio": None}
    assert ProfilePatch().model_dump(exclude_unset=True) == {}


def test_cursor_binding_and_types():
    binding = {"kind": "nodes", "viewer": str(uuid4())}
    now = datetime.now(UTC)
    identifier = uuid4()
    token = encode(binding, [now, identifier])
    assert decode(token, binding, ["time", "uuid"])[0] == [now, identifier]
    for wrong in ({"kind": "nodes", "viewer": "other"}, {"kind": "sources"}):
        with pytest.raises(Problem, match="invalid_cursor"):
            decode(token, wrong, ["time", "uuid"])
    for bad in (
        "%%",
        "x" * 2049,
        encode(binding, [datetime.now(), identifier]),
        encode(binding, [True]),
    ):
        with pytest.raises(Problem, match="invalid_cursor"):
            decode(bad, binding, ["time", "uuid"])
    timed = encode(binding, [None, 1], as_of=now)
    assert decode(timed, binding, ["nullable_time", "id"], timed=True) == ([None, 1], now)
    with pytest.raises(Problem, match="invalid_cursor"):
        decode(encode(binding, [True]), binding, ["uuid"])


def test_streak_and_window_boundaries():
    today = date(2026, 10, 6)
    assert streaks([], today) == (0, 0)
    assert streaks([today - timedelta(days=i) for i in (1, 2, 3, 5)], today) == (3, 3)
    assert streaks([today - timedelta(days=2)], today) == (0, 1)
    assert window(date(2024, 1, 1), date(2024, 12, 31), today, 366) == (
        date(2024, 1, 1),
        date(2024, 12, 31),
    )
    for start, end, future in (
        (today, None, False),
        (today, today - timedelta(days=1), False),
        (today - timedelta(days=1), today, True),
        (today, today + timedelta(days=366), False),
    ):
        with pytest.raises(Problem, match="invalid_date_window"):
            window(start, end, today, 366, future=future)
