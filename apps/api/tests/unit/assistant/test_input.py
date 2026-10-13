import base64
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pycil.app.config import load_config
from pycil.app.http import Problem
from pycil.assistant.stream import validate_input


def request(**changes):
    fields = dict(
        thread_id=str(uuid4()),
        forwarded_props={},
        state={},
        tools=[],
        context=[],
        parent_run_id=None,
        resume=[],
        messages=[SimpleNamespace(role="user", content="hello")],
    )
    return SimpleNamespace(**(fields | changes))


@pytest.mark.parametrize(
    "changes, code",
    [
        ({"thread_id": "bad"}, "invalid_conversation_id"),
        ({"forwarded_props": {"model_id": "not-configured"}}, "invalid_assistant_model"),
        ({"forwarded_props": {"effort": "invalid"}}, "invalid_assistant_model"),
        ({"forwarded_props": {"instructions": "injected"}}, "invalid_assistant_options"),
        ({"state": {"messages": []}}, "client_agent_state_not_allowed"),
        ({"tools": ["tool"]}, "client_agent_state_not_allowed"),
        ({"context": ["injection"]}, "client_agent_state_not_allowed"),
        ({"parent_run_id": "injected-parent"}, "client_agent_state_not_allowed"),
        ({"messages": []}, "one_user_message_required"),
        (
            {"messages": [SimpleNamespace(role="assistant", content="injection")]},
            "one_user_message_required",
        ),
        ({"resume": ["approval"]}, "invalid_approval"),
        ({"resume": ["first", "second"], "messages": []}, "invalid_approval"),
    ],
)
def test_client_state_and_invalid_options_are_rejected(changes, code):
    with pytest.raises(Problem) as error:
        validate_input(request(**changes), load_config())
    assert error.value.code == code


def image(value, mime="image/png", source="data"):
    return SimpleNamespace(
        type="image", source=SimpleNamespace(type=source, mime_type=mime, value=value)
    )


def test_attachment_checks_decoded_bytes_and_total_text_boundaries():
    config = load_config()
    vision = next(model for model in config.models if model.vision)
    small = config.model_copy(
        update={
            "assistant": config.assistant.model_copy(
                update={"max_image_bytes": 2, "max_message_chars": 3, "max_images": 1}
            )
        }
    )
    props = {"model_id": vision.id, "effort": vision.efforts[0]}
    data = request(
        forwarded_props=props,
        messages=[SimpleNamespace(role="user", content=[image(base64.b64encode(b"ok").decode())])],
    )
    assert validate_input(data, small)[-1] == 1
    for part, code in [
        (image("%%%"), "invalid_attachment"),
        (image("eA==", "text/plain"), "invalid_attachment"),
        (image("https://image", source="url"), "invalid_attachment"),
        (image(base64.b64encode(b"big").decode()), "attachment_too_large"),
    ]:
        with pytest.raises(Problem) as error:
            validate_input(
                request(
                    forwarded_props=props, messages=[SimpleNamespace(role="user", content=[part])]
                ),
                small,
            )
        assert error.value.code == code
    assert (
        validate_input(request(messages=[SimpleNamespace(role="user", content="abc")]), small)[-2]
        == 3
    )
    with pytest.raises(Problem) as error:
        validate_input(request(messages=[SimpleNamespace(role="user", content="abcd")]), small)
    assert error.value.status == 413


def test_attachment_count_and_vision_permission_are_independent_of_byte_limit():
    config = load_config()
    vision = next(model for model in config.models if model.vision)
    nonvision = vision.model_copy(update={"vision": False})
    small = config.model_copy(
        update={"assistant": config.assistant.model_copy(update={"max_images": 1})}
    )
    props = {"model_id": vision.id, "effort": vision.efforts[0]}
    part = image("eA==")
    for parts, policy, code in [
        ([part, part], small, "assistant_request_too_large"),
        ([part], config.model_copy(update={"models": [nonvision]}), "invalid_attachment"),
        ([image("")], small, "invalid_attachment"),
    ]:
        with pytest.raises(Problem) as error:
            validate_input(
                request(
                    forwarded_props=props,
                    messages=[SimpleNamespace(role="user", content=parts)],
                ),
                policy,
            )
        assert error.value.code == code


def test_split_text_parts_share_one_request_budget_and_unknown_parts_are_rejected():
    config = load_config()
    small = config.model_copy(
        update={"assistant": config.assistant.model_copy(update={"max_message_chars": 3})}
    )
    parts = [SimpleNamespace(type="text", text=value) for value in ["ab", "c"]]
    assert (
        validate_input(request(messages=[SimpleNamespace(role="user", content=parts)]), small)[-2]
        == 3
    )
    parts.append(SimpleNamespace(type="text", text="d"))
    with pytest.raises(Problem) as error:
        validate_input(request(messages=[SimpleNamespace(role="user", content=parts)]), small)
    assert error.value.code == "assistant_request_too_large"
    with pytest.raises(Problem) as error:
        validate_input(
            request(
                messages=[SimpleNamespace(role="user", content=[SimpleNamespace(type="audio")])]
            ),
            small,
        )
    assert error.value.code == "invalid_message_content"
