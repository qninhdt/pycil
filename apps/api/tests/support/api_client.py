"""A thin client over the running stack, for system journeys.

System tests talk to a real API over a socket, so every journey needs the same three
things: a bearer token for a Clerk subject, a request that raises on an unexpected
status, and a way to see the envelope when one is unexpected. This module is those
three things and nothing else — it deliberately does not model the product, because a
client that knows what the API means would hide the contract the journeys are here to
check.
"""

from __future__ import annotations

from typing import Any

import httpx

from tests.support.clerk_jwks import bearer


class Api:
    """One caller against the running API, with or without a credential."""

    def __init__(self, client: httpx.AsyncClient, token: str | None) -> None:
        self._client = client
        self._headers = bearer(token) if token else {}

    @classmethod
    def for_subject(cls, client: httpx.AsyncClient, clerk_stub, subject, email: str) -> Api:
        """A caller whose Clerk subject is new, so its account cannot pre-exist."""
        return cls(client, clerk_stub.token(subject=subject, email=email))

    @classmethod
    def anonymous(cls, client: httpx.AsyncClient) -> Api:
        """No credential at all — a shared link opened by someone with no account."""
        return cls(client, None)

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._headers)

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self._client.get(path, headers=self.headers, **kwargs)

    async def post(self, path: str, json: Any = None, **kwargs: Any) -> httpx.Response:
        return await self._client.post(path, headers=self.headers, json=json, **kwargs)

    async def patch(self, path: str, json: Any = None, **kwargs: Any) -> httpx.Response:
        return await self._client.patch(path, headers=self.headers, json=json, **kwargs)

    async def delete(self, path: str, json: Any = None, **kwargs: Any) -> httpx.Response:
        """DELETE, optionally with a body.

        httpx's own ``delete`` takes no ``json``, so a route that requires a
        confirmation payload — as account deletion does — has to be reached through
        ``request``. A helper that silently dropped the body would turn a product
        refusal into a transport error.
        """
        return await self._client.request(
            "DELETE", path, headers=self.headers, json=json, **kwargs
        )

    # --- calls that assert their own status ---------------------------------
    #
    # A journey that continues after an unexpected status produces a confusing
    # failure somewhere else. These raise with the envelope in the message, which is
    # the whole diagnostic: the API's error bodies carry a stable code.

    async def ok(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._client.request(method, path, headers=self.headers, **kwargs)
        assert response.status_code < 400, (
            f"{method} {path} -> {response.status_code} {response.text}"
        )
        return None if response.status_code == 204 else response.json()

    async def status(self, method: str, path: str, expected: int, **kwargs: Any) -> httpx.Response:
        response = await self._client.request(method, path, headers=self.headers, **kwargs)
        assert response.status_code == expected, (
            f"{method} {path} -> {response.status_code}, expected {expected}: {response.text}"
        )
        return response

    # --- the product calls the journeys actually make ------------------------

    async def create_node(
        self,
        *,
        node_type: str,
        name: str,
        parent_id: str | None = None,
        target_id: str | None = None,
        visibility: str = "PRIVATE",
        confirm_subtree_publication: bool = False,
    ) -> dict:
        return await self.ok(
            "POST",
            "/v1/nodes",
            json={
                "type": node_type,
                "name": name,
                "parentNodeId": parent_id,
                "targetNodeId": target_id,
                "visibility": visibility,
                "confirmSubtreePublication": confirm_subtree_publication,
            },
        )

    async def folder(self, name: str, *, parent_id: str | None = None, **kwargs) -> dict:
        """A folder. Publishing one is a subtree decision, so it needs confirmation.

        The server refuses a public folder without it, because publishing a folder
        publishes everything inside it now and later. Defaulting the confirmation here
        keeps a test's setup about the scenario rather than about that rule; the rule
        itself is asserted in its own journey.
        """
        if kwargs.get("visibility") == "PUBLIC":
            kwargs.setdefault("confirm_subtree_publication", True)
        return await self.create_node(
            node_type="FOLDER", name=name, parent_id=parent_id, **kwargs
        )

    async def deck(self, name: str, *, parent_id: str | None = None, **kwargs) -> dict:
        return await self.create_node(
            node_type="DECK", name=name, parent_id=parent_id, **kwargs
        )

    async def reference(self, name: str, target_id: str, *, parent_id: str | None = None) -> dict:
        return await self.create_node(
            node_type="REFERENCE", name=name, target_id=target_id, parent_id=parent_id
        )

    async def add_sense(self, deck_id: str, sense_id: int) -> dict:
        return await self.ok("POST", f"/v1/decks/{deck_id}/senses", json={"senseId": sense_id})

    async def deck_sense_ids(self, deck_id: str) -> list[int]:
        items = await self.ok("GET", f"/v1/decks/{deck_id}/items")
        return [item["senseId"] for item in items]

    async def start_session(self, node_id: str) -> dict:
        return await self.ok("POST", "/v1/sessions", json={"nodeId": node_id})

    async def next_question(self, session_id: str) -> dict:
        return await self.ok("GET", f"/v1/sessions/{session_id}/next")

    async def answer(self, session_id: str, question_id: int, answer: str) -> dict:
        return await self.ok(
            "POST",
            "/v1/answers",
            json={"sessionId": session_id, "questionId": question_id, "answer": answer},
        )

    async def session(self, session_id: str) -> dict:
        return await self.ok("GET", f"/v1/sessions/{session_id}")

    async def credit(self) -> dict:
        return await self.ok("GET", "/v1/me/credit")

    async def me(self) -> dict:
        return await self.ok("GET", "/v1/me")
