"""Per-turn provider client construction.

The graph is compiled once per process, but a learner may select a different
enabled model for a turn. Building the client here keeps that decision in one
place, so the compiled default and a per-turn switch cannot drift apart in how
they configure the provider.
"""

from langchain_openai import ChatOpenAI

from pycil.config import settings
from pycil.product_config import system_config


def build_chat_model(model_id: str, max_output_tokens: int, reasoning_effort: str | None = None):
    """A provider client for one model, with the selected reasoning effort.

    ``none`` means "send no reasoning parameter at all" rather than the string
    ``none``: the provider treats an absent field and an explicit ``none``
    differently on some routes.
    """
    extra_body = None
    if reasoning_effort and reasoning_effort != "none":
        extra_body = {"reasoning_effort": reasoning_effort}
    return ChatOpenAI(
        model=model_id,
        api_key=settings.assistant_api_key,
        base_url=settings.assistant_base_url,
        timeout=system_config.assistant.turn_timeout_seconds,
        max_completion_tokens=max_output_tokens,
        streaming=True,
        max_retries=0,
        extra_body=extra_body,
    )
