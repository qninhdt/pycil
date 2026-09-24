"""Fixtures for system-level journeys.

One stack per session, isolation per test by identity. Starting Postgres, a worker and
a migration pass costs seconds; doing it for every test would put the suite past the
point where anyone runs it before pushing.

Isolation is by unique Clerk subject rather than by a clean database. Every test signs
in as a subject nobody else has used, so rows never collide and no test depends on
another's data being absent.

Two things are worth stating about what the fixtures here do *not* do:

- **They never write to Redis or PostgreSQL to make a flow pass.** A journey drives the
  product through HTTP; a fixture may seed before it and inspect after it, but a
  mid-flow write would replace the code path the journey exists to exercise.
- **The external services are doubled only at their network boundary.** The stack
  processes are handed a JWKS URL and an LLM base URL. Everything else — the database,
  Redis, the job stream, Lexi — is the real thing.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterator

import httpx
import pytest
import pytest_asyncio

from tests.support import lexi_seed
from tests.support import stack as stack_support
from tests.support.api_client import Api
from tests.support.clerk_jwks import AUDIENCE, ISSUER
from tests.support.llm_gateway import start_gateway
from tests.support.stack import SystemStack

#: Tests that need the whole product running. Skipped rather than failed when the
#: machine cannot provide it, because "no Docker here" is a fact about the
#: environment, not a defect in the code under test.
requires_stack = pytest.mark.skipif(
    not stack_support.stores_available(),
    reason="system tests need Docker or TEST_STACK_DB_URL/TEST_STACK_REDIS_URL",
)


@pytest.fixture(scope="session")
def llm_gateway() -> Iterator[object]:
    """The provider every stack process talks to.

    Session-scoped, and the *same server* the whole run shares. That is deliberate: the
    gateway counts the calls it receives, and several journeys assert on that count
    (one generation for two concurrent requests, no provider call for a rejected model).
    A per-test server would make those counts start from zero and prove less.
    """
    gateway = start_gateway()
    try:
        yield gateway
    finally:
        gateway.stop()


@pytest.fixture(scope="session")
def clerk_stub() -> Iterator[object]:
    """A real JWKS endpoint the API process fetches keys from over HTTP.

    Independent of the in-process stub the integration level uses: this one's URL is
    handed to a *separate process*, so verification runs exactly as it does in
    deployment rather than through a monkeypatched client.
    """
    from tests.support.clerk_jwks import ClerkStub

    stub = ClerkStub()
    stub.start()
    try:
        yield stub
    finally:
        stub.stop()


@pytest.fixture(scope="session")
def system_stack(llm_gateway, clerk_stub) -> Iterator[SystemStack]:
    stack_support.require_reference_dataset()
    stack, lifecycle = stack_support.start_stack(
        clerk_jwks_url=clerk_stub.url,
        clerk_issuer=ISSUER,
        clerk_audience=AUDIENCE,
        llm_base_url=llm_gateway.base_url,
    )
    try:
        yield stack
    finally:
        stack.stop()
        lifecycle.stop()


@pytest_asyncio.fixture
async def stack_client(system_stack) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An HTTP client bound to the running API's real port.

    Not an ASGI transport: the point of this level is that the request crosses a socket
    into a separate process, so middleware, lifespan state and the worker's shared
    database are all the ones the deployment has.
    """
    async with httpx.AsyncClient(base_url=system_stack.base_url, timeout=60.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def corpus(system_stack, clerk_stub) -> dict[str, int]:
    """A populated dictionary, generated once for the whole run.

    Question supply draws distractors from *other* words, so a dictionary holding a
    single word cannot produce a choice item at all. Every study journey therefore
    needs a population rather than one word, and the population is per word and
    shared between learners — so it belongs at session scope, not per test.

    Seeded through the product's own generation path by a caller of its own, because
    the dictionary is not owned by any learner: the words a journey studies are the
    same words whatever account generated them.
    """
    async with httpx.AsyncClient(base_url=system_stack.base_url, timeout=120.0) as client:
        caller = Api(
            client,
            clerk_stub.token(subject="user_corpus_seed", email="corpus@example.test"),
        )
        return await lexi_seed.seed(caller)


@pytest.fixture
def actor(stack_client, clerk_stub):
    """A factory for authenticated callers, each with a brand-new Clerk subject.

    A factory rather than one fixture per test because most journeys need two or three
    identities — an owner, a stranger, an anonymous reader — and they must not share an
    account. The email is derived from the subject so a link-to-existing-account flow
    cannot accidentally match another test's row.
    """

    class Actors:
        def __init__(self, client: httpx.AsyncClient, stub) -> None:
            self.client = client
            self.stub = stub

        def new(self, label: str = "learner") -> Api:
            return self.token(f"user_{uuid.uuid4().hex[:16]}", label=label)

        def token(self, subject: str, *, label: str = "learner", **claims) -> Api:
            """A caller for a caller-chosen subject, for races and repeat sign-ins."""
            return Api(
                self.client,
                self.stub.token(subject=subject, email=f"{label}-{subject}@example.test", **claims),
            )

        def with_email(self, subject: str, email: str, **claims) -> Api:
            return Api(self.client, self.stub.token(subject=subject, email=email, **claims))

        def raw_token(self, subject: str, *, email: str | None = None, **claims) -> str:
            """A bare token, for the cases that need to alter or malform one."""
            return self.stub.token(subject=subject, email=email, **claims)

        def anonymous(self) -> Api:
            return Api.anonymous(self.client)

    return Actors(stack_client, clerk_stub)


@pytest_asyncio.fixture
async def durable(system_stack) -> AsyncGenerator[Durable, None]:
    """Access to the stack's database: inspect after a flow, seed before one.

    Some contracts — one row per graded answer, one global schedule per
    ``(learner, sense)``, a ledger that did not move — have no public read that proves
    them. A journey may look *after* its HTTP effect to confirm the effect was
    singular.

    Seeding is the other half and is deliberately narrow. A journey that needs a state
    the product only reaches after real elapsed time (a sense that has come due for
    review) can set that state *before* the flow starts; the flow itself then runs
    through the product exactly as it would for a learner who waited. What is never
    allowed is a write *during* a flow to make it pass: that would replace the code
    path the journey exists to exercise, and the journey would prove nothing.
    """
    import asyncpg

    connection = await asyncpg.connect(system_stack.stores.sync_database_url)
    try:
        yield Durable(connection)
    finally:
        await connection.close()


class Durable:
    """Queries against the running stack's own database.

    Reads are for inspecting a durable effect. ``seed`` is for establishing a
    precondition before a flow — never for changing an outcome during one.
    """

    def __init__(self, connection) -> None:
        self.connection = connection

    async def seed(self, sql: str, *args) -> None:
        """Establish a precondition before a flow starts.

        Only for state the product would reach on its own given time — a schedule that
        has come due, a ledger at a particular balance. Calling this mid-flow would
        bypass the path under test, which is the one thing a system journey must not
        do.
        """
        await self.connection.execute(sql, *args)

    async def scalar(self, sql: str, *args):
        return await self.connection.fetchval(sql, *args)

    async def rows(self, sql: str, *args):
        return await self.connection.fetch(sql, *args)

    async def count(self, sql: str, *args) -> int:
        return await self.connection.fetchval(sql, *args) or 0
