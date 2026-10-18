from pycil.infrastructure.llm import merge_usage, openai_usage, record
from tests.support.inference import UsageRecorder


def response(**usage):
    return {"model": "model", "usage": usage}


def test_reported_reasoning_is_added_only_when_total_proves_it_is_separate():
    combined = response(
        prompt_tokens=10,
        completion_tokens=6,
        total_tokens=16,
        completion_tokens_details={"reasoning_tokens": 4},
    )
    separate = response(
        prompt_tokens=10,
        completion_tokens=6,
        total_tokens=20,
        completion_tokens_details={"reasoning_tokens": 4},
    )
    assert openai_usage(combined).output_tokens == 6
    assert openai_usage(separate).output_tokens == 10


def test_unknown_invalid_and_zero_usage_remain_distinct_when_aggregated():
    zero = openai_usage(
        response(prompt_tokens=0, completion_tokens=0, prompt_tokens_details={"cached_tokens": 0})
    )
    unknown = openai_usage(response(prompt_tokens=True, completion_tokens=-1))
    assert zero.input_tokens == zero.output_tokens == 0
    assert unknown.input_tokens is unknown.output_tokens is None
    merged = merge_usage([zero, unknown])
    assert len(merged) == 1
    assert merged[0].input_tokens is merged[0].output_tokens is None


def test_operation_usage_scopes_restore_parent_and_attach_failed_attempts():
    one = openai_usage(response(prompt_tokens=10, completion_tokens=2))
    with UsageRecorder() as outer:
        record(one)
        error = RuntimeError("failure")
        try:
            with UsageRecorder():
                record(one)
                raise error
        except RuntimeError:
            pass
        record(one)
        assert outer.finish(None)[1][0].input_tokens == 20
    assert error.usage[0].input_tokens == 10
