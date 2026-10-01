"""Attachment admission and history sanitization.

The proxy already bounds the request body, so these tests cover what it cannot:
which media types are admissible, how many, whether the selected model can see an
image, and that a past turn's bytes do not ride along on every later request.
"""

import pytest
from ag_ui.core import DataSource, ImageInputContent, TextInputContent, UserMessage
from langchain_core.messages import AIMessage, HumanMessage

from pycil.assistant.agent.attachments import (
    IMAGE_PLACEHOLDER,
    AttachmentRejected,
    strip_historical_images,
    validate_attachments,
)


def _image_part(mime_type: str = "image/jpeg") -> ImageInputContent:
    return ImageInputContent(
        type="image",
        source=DataSource(type="data", value="aGVsbG8=", mime_type=mime_type),
    )


def _text_part(text: str = "describe this") -> TextInputContent:
    return TextInputContent(type="text", text=text)


def _user_message(*parts) -> UserMessage:
    """A multimodal user message; a bare string is a text part, not a list item."""
    content = [part if not isinstance(part, str) else _text_part(part) for part in parts]
    return UserMessage(id="m1", role="user", content=content)


def _image_block(mime_type: str = "image/jpeg") -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,aGVsbG8="}}


def test_a_supported_image_is_admitted_for_a_vision_model():
    validate_attachments([_user_message("describe this", _image_part())], vision_enabled=True)


def test_an_unsupported_media_type_is_refused():
    with pytest.raises(AttachmentRejected) as rejected:
        validate_attachments([_user_message(_image_part("image/gif"))], vision_enabled=True)

    assert rejected.value.code == "assistant_attachment_type_unsupported"


def test_an_image_without_a_declared_type_is_refused():
    part = ImageInputContent(
        type="image", source=DataSource(type="data", value="aGVsbG8=", mime_type="")
    )

    with pytest.raises(AttachmentRejected) as rejected:
        validate_attachments([_user_message(part)], vision_enabled=True)

    assert rejected.value.code == "assistant_attachment_mime_unknown"


def test_a_model_without_vision_refuses_an_image():
    """The refusal must land before the provider call, not as a provider 400."""
    with pytest.raises(AttachmentRejected) as rejected:
        validate_attachments([_user_message(_image_part())], vision_enabled=False)

    assert rejected.value.code == "assistant_attachment_model_has_no_vision"


def test_more_than_one_image_in_a_turn_is_refused():
    with pytest.raises(AttachmentRejected) as rejected:
        validate_attachments([_user_message(_image_part(), _image_part())], vision_enabled=True)

    assert rejected.value.code == "assistant_attachment_too_many"


def test_a_text_only_turn_passes_without_vision():
    validate_attachments([_user_message("hello")], vision_enabled=False)


def test_history_keeps_the_current_image_and_replaces_earlier_ones():
    history = [
        HumanMessage(content=["first question", _image_block()]),
        AIMessage(content="first answer"),
        HumanMessage(content=["second question", _image_block("image/png")]),
    ]

    cleaned = strip_historical_images(history)

    assert cleaned[0].content[1] == IMAGE_PLACEHOLDER
    # The current turn's image is the one the provider still needs to see.
    assert cleaned[2].content[1] == _image_block("image/png")
    assert cleaned[1].content == "first answer"


def test_a_remote_image_reference_is_left_alone():
    """A URL block carries no bytes, so replacing it would lose information."""
    remote = {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}}
    history = [
        HumanMessage(content=["q1", remote]),
        HumanMessage(content="q2"),
    ]

    cleaned = strip_historical_images(history)

    assert cleaned[0].content[1] == remote
