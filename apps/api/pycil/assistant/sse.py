"""The SSE wire contract for the assistant's streaming routes.

Framing itself lives in the router (`_stream`, `_event_frame`); this module holds
the published contract a client codes against: the event schema and the OpenAPI
metadata that advertises it.
"""

from pydantic import BaseModel, ConfigDict, Field


class AssistantSSEEvent(BaseModel):
    """Named contract for one logical event encoded in the SSE response stream."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(description="Monotonically increasing event id for reconnection.")
    event: str = Field(description="Event type, such as token, action, error, or done.")
    data: dict = Field(description="Sanitized JSON event payload.")


SSE_RESPONSE = {
    200: {
        "model": AssistantSSEEvent,
        "description": "A recoverable server-sent event stream.",
        "content": {
            "text/event-stream": {
                "schema": {
                    "type": "string",
                    "description": "SSE frames; each data payload matches AssistantSSEEvent.",
                    "x-pycil-sse-event-schema": "#/components/schemas/AssistantSSEEvent",
                }
            }
        },
    }
}
SSE_OPENAPI_EXTENSION = {
    "x-pycil-sse-contract": {
        "eventSchema": "#/components/schemas/AssistantSSEEvent",
        "frame": "id: <sequence>\\nevent: <event>\\ndata: <json>\\n\\n",
        "reconnectHeader": "Last-Event-ID",
    }
}
