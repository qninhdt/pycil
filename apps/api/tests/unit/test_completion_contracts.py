import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pycil.account.schemas import PreferencesPatch, ProfilePatch
from pycil.http import Problem
from pycil.pagination import decode, encode
from pycil.study.progress import window
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
    def result(identifier, correct):
        return dict(
            question_artifact_id=identifier,
            question_type="WORD_TO_DEFINITION",
            format="SINGLE_CHOICE",
            diagnostics=dict(correct=correct),
            answered_at="2026-10-11T00:00:00Z",
        )

    a = ReviewBatch(results=[result(1, True), result(2, False)])
    b = ReviewBatch(results=[dict(reversed(list(item.model_dump().items()))) for item in a.results])
    assert request_hash(a) == request_hash(b)
    assert request_hash(a) != request_hash(ReviewBatch(results=list(reversed(a.results))))
    assert len(ReviewBatch(results=[result(1, True)] * 60).results) == 60
    with pytest.raises(ValidationError):
        ReviewBatch(results=[result(1, True)] * 61)


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
    assert ProfilePatch(handle="  NiNh_123 ", bio=" Hello ").model_dump(exclude_unset=True) == {
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


def test_window_boundaries():
    today = date(2026, 10, 6)
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


@pytest.mark.parametrize(
    "label,inf", [("", "BASE"), ("p", "PAST"), ("PP", "PAST_PARTICIPLE"), ("3", "PRESENT_3SG")]
)
def test_native_markup_normalizes_labels_without_changing_learner_text(label, inf):
    from lexi_ai.text import canonical_markup, parse_marked_example

    content = f"🌍 [Harbor{'|' + label if label else ''}]."
    assert canonical_markup(content) == f"🌍 [Harbor{'|' + label.lower() if label else ''}]."
    text, spans = parse_marked_example(content)
    assert text == "🌍 Harbor."
    assert spans[0].surface == "Harbor"
    assert spans[0].inf.value == inf


@pytest.mark.parametrize("examples", [[], ["No target."], ["[word|unknown]"]])
def test_native_enrichment_retries_when_no_examples_are_usable(examples):
    from lexi_ai.words.schemas import SenseEnrichment

    with pytest.raises(ValidationError, match="no usable examples"):
        SenseEnrichment.model_validate(
            {
                "tier": "core",
                "examples": examples,
                "forms": [],
                "patterns": [],
                "collocations": [],
                "relations": {},
                "cefr_level": "b1",
                "register": None,
            }
        )


@pytest.mark.parametrize("count", [1, 3, 5, 6])
def test_native_examples_request_three_but_accept_any_nonempty_usable_output(count):
    from lexi_ai.inference.prompting import render_prompt
    from lexi_ai.words.schemas import SenseEnrichment

    instruction, data = render_prompt(
        "words/prompts/enrich_sense.jinja",
        word={"lemma": "harbor", "type": "WORD", "aliases": []},
        senses=[{"sense_id": 1, "definition": "a sheltered place", "pos": "NOUN"}],
        examples_per_sense=3,
    )
    assert "Write exactly `examples_per_sense` natural sentences" in instruction
    context = json.loads(
        data.removeprefix("<sense_request>").removesuffix("</sense_request>").strip()
    )
    assert context["examples_per_sense"] == 3
    assert "return fewer or more" not in instruction
    schema = SenseEnrichment.model_json_schema()["properties"]["examples"]
    assert schema["minItems"] == 1
    assert "maxItems" not in schema
    output = SenseEnrichment.model_validate(
        {
            "tier": "core",
            "examples": [f"Ships enter the [harbor] ({i})." for i in range(count)],
            "forms": [],
            "patterns": [],
            "collocations": [],
            "relations": {},
            "cefr_level": "b1",
            "register": None,
        }
    )
    assert len(output.examples) == count
