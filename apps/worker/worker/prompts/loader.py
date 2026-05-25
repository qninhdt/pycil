"""Vanilla Jinja2 prompt loader.

Templates live under apps/worker/prompts/. Use built-in `{% include "role.md" %}`
for shared blocks. No custom directives.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        autoescape=select_autoescape(default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(template_name: str, **context) -> str:
    return _env().get_template(template_name).render(**context)
