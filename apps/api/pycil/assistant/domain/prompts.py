"""Stable assistant prompt and deterministic cache-prefix helpers.

The system prompt is authored as a Jinja template under ``prompt_templates/`` and
rendered once, at import time, into the ``SYSTEM_PROMPT`` string that the rest of
the package consumes. Rendering uses only static, code-owned context (no request-
or time-varying data), so the result is deterministic and safe to include in the
cacheable prompt prefix.
"""

import json
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from pycil.assistant.domain.external_data import EXTERNAL_DATA_KEY

PROMPT_VERSION = "assistant-v2"

_TEMPLATE_DIR = Path(__file__).parent / "prompt_templates"
_SYSTEM_TEMPLATE = "system.jinja"

# Code-owned prompt context. These lists are the single source of truth for the
# assistant's boundaries and are kept in sync with the tool policy enforced in the
# agent graph (e.g. the sensitive tools gated by human-in-the-loop approval).
ALLOWED_DOMAINS: tuple[str, ...] = (
    "their folders",
    "decks and the words or senses inside them (deck content)",
    "dictionary search",
    "word generation",
    "folder statistics",
)

FORBIDDEN_FEATURES: tuple[str, ...] = (
    "shell or filesystem access",
    "reference management",
    "learning-session control",
    "response grading",
    "account administration",
)

# Mirrors the sensitive tools wired into HumanInTheLoopMiddleware in
# ``pycil.assistant.application.graph`` (move_node, publish_node, delete_node,
# remove_senses_from_deck).
SENSITIVE_ACTIONS: tuple[str, ...] = (
    "moving a node (`move_node`)",
    "publishing or making a node public (`publish_node`)",
    "deleting a node (`delete_node`)",
    "removing senses from a deck (`remove_senses_from_deck`)",
)


@lru_cache(maxsize=1)
def _environment() -> Environment:
    """Build the Jinja environment once; templates are static, code-owned assets."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,  # plain-text prompt: do not HTML-escape quotes/ampersands
        undefined=StrictUndefined,  # surface missing variables at import, not silently
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )


def render_system_prompt() -> str:
    """Render the assistant system prompt from its Jinja template."""
    template = _environment().get_template(_SYSTEM_TEMPLATE)
    rendered = template.render(
        allowed_domains=ALLOWED_DOMAINS,
        forbidden_features=FORBIDDEN_FEATURES,
        sensitive_actions=SENSITIVE_ACTIONS,
        external_data_key=EXTERNAL_DATA_KEY,
    )
    return rendered.strip()


SYSTEM_PROMPT = render_system_prompt()


def stable_prompt_prefix(tools: Iterable[Any], summary: str = "") -> str:
    """Serialize the cacheable prompt prefix without time- or request-varying data."""
    definitions = []
    for tool in tools:
        if isinstance(tool, Mapping):
            definitions.append(dict(tool))
            continue
        schema = getattr(tool, "args_schema", None)
        if hasattr(schema, "model_json_schema"):
            schema = schema.model_json_schema()
        definitions.append(
            {
                "name": getattr(tool, "name", ""),
                "description": getattr(tool, "description", "") or "",
                "args": schema or {},
            }
        )
    return json.dumps(
        {
            "promptVersion": PROMPT_VERSION,
            "tools": definitions,
            "system": SYSTEM_PROMPT,
            "summary": summary,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
