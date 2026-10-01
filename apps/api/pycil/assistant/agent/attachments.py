"""Attachment admission and history sanitization for the assistant.

An image reaches the model as inline base64 inside the AG-UI request, which the
adapter converts to a LangChain ``image_url`` block. Two things follow, and both
are handled here rather than in the client:

* **Admission.** The declared media type, the count, and whether the selected
  model can see an image at all are checked before any provider call, so a
  rejected attachment costs the learner nothing. The payload size is already
  bounded by the proxy's request cap; decoding it here would pay that cost before
  the refusal.
* **History.** A checkpoint stores the conversation, so a turn that re-sent every
  past image would grow the request until it hit the provider's limit — while
  charging the learner again for input tokens the provider already processed.
  Only the current turn's image is sent whole; earlier ones become a marker.

This is a size and cost boundary, not a security one: a data URL is data to the
model either way, and the tool layer is what enforces authorization.
"""

from ag_ui.core import ImageInputContent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage

#: Image formats a vision model accepts. Deliberately an allowlist: an unknown
#: type is a client bug or an attempt to smuggle a non-image through the image
#: path, and both should fail at the boundary rather than at the provider.
ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

#: One image per turn. A larger batch is not a product need yet, and bounding the
#: count keeps the worst-case request size predictable.
MAX_IMAGES_PER_TURN = 1

#: Stands in for image bytes once their turn has passed. Says what was there
#: without carrying it, so the model can still follow the conversation.
IMAGE_PLACEHOLDER = "[image sent earlier in this conversation]"


class AttachmentRejected(Exception):
    """An attachment cannot be admitted, with a stable reason code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _image_mime_type(part: ImageInputContent) -> str:
    source = part.source
    mime_type = getattr(source, "mime_type", None)
    if not isinstance(mime_type, str) or not mime_type:
        raise AttachmentRejected("assistant_attachment_mime_unknown")
    return mime_type.lower().split(";", 1)[0].strip()


def validate_attachments(messages, *, vision_enabled: bool) -> None:
    """Refuse an inadmissible attachment before the provider is called.

    Raises :class:`AttachmentRejected` with a stable code, which the router turns
    into a 4xx.
    """
    total = 0
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, ImageInputContent):
                continue
            total += 1
            if total > MAX_IMAGES_PER_TURN:
                raise AttachmentRejected("assistant_attachment_too_many")
            if _image_mime_type(part) not in ALLOWED_IMAGE_MIME_TYPES:
                raise AttachmentRejected("assistant_attachment_type_unsupported")
            if not vision_enabled:
                raise AttachmentRejected("assistant_attachment_model_has_no_vision")


def _is_inline_image_block(block) -> bool:
    """A LangChain media block carrying inline image bytes.

    The adapter emits ``image_url`` for every image, with the payload inside a
    ``data:`` URL. A remote-URL block is not matched: it carries a reference
    rather than bytes, so re-sending it costs no tokens to re-encode.
    """
    if not isinstance(block, dict) or block.get("type") != "image_url":
        return False
    payload = block.get("image_url")
    url = payload.get("url") if isinstance(payload, dict) else None
    return isinstance(url, str) and url.startswith("data:")


def strip_historical_images(messages) -> list:
    """Replace image bytes in every message except the most recent one.

    The last user message is the current turn, so its image is left whole. A
    completed turn leaves the marker behind, which is what stops the next request
    from re-uploading bytes the provider has already been paid for.
    """
    current = max(
        (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=None,
    )
    cleaned = []
    for index, message in enumerate(messages):
        content = getattr(message, "content", None)
        if index == current or not isinstance(content, list):
            cleaned.append(message)
            continue
        if not any(_is_inline_image_block(block) for block in content):
            cleaned.append(message)
            continue
        parts = [IMAGE_PLACEHOLDER if _is_inline_image_block(block) else block for block in content]
        cleaned.append(message.model_copy(update={"content": parts}))
    return cleaned


class HistoricalImageMiddleware(AgentMiddleware):
    """Send only the current turn's image to the provider."""

    async def awrap_model_call(self, request, handler):
        messages = strip_historical_images(request.messages)
        return await handler(request.override(messages=messages))
