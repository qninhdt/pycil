"""Stable assistant prompt.

The system prompt is authored as a Jinja template under ``prompts/`` and
rendered once, at import time, into the ``SYSTEM_PROMPT`` string that the rest of
the package consumes. Rendering uses only static, code-owned context (no request-
or time-varying data), so the result is deterministic.
"""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATE_DIR = Path(__file__).parent / "prompts"
_SYSTEM_TEMPLATE = "system.jinja"

# Code-owned prompt context. These lists are the single source of truth for the
# assistant's boundaries and are kept in sync with the tool policy enforced in the
# agent graph (e.g. the sensitive tools gated by human-in-the-loop approval).
ALLOWED_DOMAINS: tuple[str, ...] = (
    "their folders",
    "decks and the words or senses inside them (deck content)",
    "dictionary search",
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
# ``pycil.assistant.agent.graph`` (move_node, publish_node, delete_node,
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
    )
    return rendered.strip()


SYSTEM_PROMPT = render_system_prompt()
