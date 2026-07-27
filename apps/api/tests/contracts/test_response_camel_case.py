"""No response body may expose a snake_case property.

The web client used to normalise this itself with a blanket recursive
snake-to-camel transform over every response body. That is why the drift went
unnoticed: several DTOs were never aliased at all and only *appeared* camelCase
downstream. Deleting the transform — which the frontend rebuild does — would have
silently nulled every unaliased field, including ``tokenVersion``, the auth
revocation counter, with a completely green typecheck.

So the contract is enforced here, at the source, rather than patched at the edge.

REQUEST bodies are deliberately out of scope: ``refresh_token`` is what clients
already send, and renaming it would break callers for no benefit.
"""

import re

import pytest

from pycil.main import create_app

pytestmark = pytest.mark.asyncio

_SNAKE = re.compile(r"[a-z0-9]_[a-z0-9]")

# Free-form JSON objects whose KEYS are data, not contract. An account export
# mirrors row shapes, and an assistant/question payload is opaque to pycil.
_OPAQUE_PROPERTIES = frozenset({"profile", "learning", "assistant", "payload", "reveal"})


def _schema_names_in(node, out: set[str]) -> None:
    """Collect every component schema name reachable from a response schema."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            out.add(ref.rsplit("/", 1)[1])
        for value in node.values():
            _schema_names_in(value, out)
    elif isinstance(node, list):
        for value in node:
            _schema_names_in(value, out)


def _response_schema_names(document: dict) -> set[str]:
    names: set[str] = set()
    for methods in document["paths"].values():
        for operation in methods.values():
            if not isinstance(operation, dict):
                continue
            for response in operation.get("responses", {}).values():
                for media in response.get("content", {}).values():
                    _schema_names_in(media.get("schema"), names)
    # Close over nested refs: a response DTO that embeds another DTO must be
    # checked too, or the deepest fields are the ones that escape.
    schemas = document["components"]["schemas"]
    frontier = set(names)
    while frontier:
        nested: set[str] = set()
        for name in frontier:
            _schema_names_in(schemas.get(name), nested)
        frontier = nested - names
        names |= nested
    return names


def _snake_properties(document: dict, names: set[str]) -> list[str]:
    offenders: list[str] = []
    schemas = document["components"]["schemas"]
    for name in sorted(names):
        for prop in sorted(schemas.get(name, {}).get("properties", {})):
            if prop in _OPAQUE_PROPERTIES:
                continue
            if _SNAKE.search(prop):
                offenders.append(f"{name}.{prop}")
    return offenders


async def test_no_response_schema_exposes_a_snake_case_property():
    document = create_app().openapi()

    names = _response_schema_names(document)
    assert names, "no response schemas found — the walker is broken, not the API"

    offenders = _snake_properties(document, names)
    assert offenders == [], (
        "these response fields reach the client as snake_case; add a "
        "serialization_alias rather than transforming them client-side:\n"
        + "\n".join(offenders)
    )


async def test_the_walker_would_actually_catch_an_offender():
    """A guard that cannot fail is not a guard.

    Injects a snake_case property into a schema the walker reached and asserts it
    is reported, so a refactor that quietly stops traversing responses fails here
    instead of passing vacuously.
    """
    document = create_app().openapi()
    names = _response_schema_names(document)
    victim = sorted(names)[0]
    document["components"]["schemas"][victim].setdefault("properties", {})[
        "injected_snake_field"
    ] = {"type": "string"}

    assert f"{victim}.injected_snake_field" in _snake_properties(document, names)


async def test_token_version_is_absent_from_the_me_response():
    """The revocation counter is server state and must not ship to a browser."""
    document = create_app().openapi()

    me = document["paths"]["/v1/me"]["get"]["responses"]["200"]["content"]["application/json"]
    name = me["schema"]["$ref"].rsplit("/", 1)[1]
    properties = document["components"]["schemas"][name]["properties"]

    assert set(properties) == {"id", "email", "name", "image"}
    assert "token_version" not in properties
    assert "tokenVersion" not in properties


async def test_request_bodies_keep_their_snake_case_names():
    """Out of scope on purpose — renaming these would break existing callers."""
    document = create_app().openapi()
    schemas = document["components"]["schemas"]

    assert "refresh_token" in schemas["RefreshRequest"]["properties"]
    assert "refresh_token" in schemas["LogoutRequest"]["properties"]
