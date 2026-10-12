"""Opt-in real Clerk/browser suite; stores are owned by scripts/test_api.py."""

import asyncio
import json
import os
import re
import secrets
import signal
import socket
import sqlite3
from contextlib import AsyncExitStack, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import uvicorn
from dotenv import dotenv_values
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import SecretStr, ValidationError
from sqlalchemy import text
from typesafe_sdk import Choice

from pycil.account.auth import Identity
from pycil.account.models import User
from pycil.account.plans import Feature, Plan
from pycil.account.usage import settle
from pycil.assistant import graph as agents
from pycil.dependencies import process_resources
from pycil.library.tree import provision_library
from pycil.main import create_app
from pycil.study.fsrs import next_state
from pycil.study.models import UserSense
from tests.integration.test_assistant import Completion, answer
from tests.integration.test_learning_pipeline import LocalCompletion, fill

pytest_plugins = ["tests.integration.test_learning_pipeline"]
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_WEB_E2E") != "1", reason="Run the opt-in real Clerk/browser profile"
)
ROOT = Path(__file__).resolve().parents[4]


class BrowserLexicalCompletion(LocalCompletion):
    failed_once = False

    async def complete(self, instruction, data, schema):
        if schema.__name__ not in {"InventoryOutput", "EnrichmentBatch"}:
            return await super().complete(instruction, data, schema)
        context = json.loads(re.sub(r"</?\w+>", "", data).strip())
        target = (
            context["target"] if schema.__name__ == "InventoryOutput" else context["word"]["lemma"]
        )
        if schema.__name__ == "InventoryOutput":
            if target == "quay" and not self.failed_once:
                self.failed_once = True
                raise ValueError("deterministic provider failure")
            return {
                "lemma": (
                    "glisten with {sth}"
                    if target == "glisten with something"
                    else "glisten"
                    if target in {"glistening", "glistened"}
                    else target
                ),
                "type": "PHRASAL_VERB" if target == "glisten with something" else "WORD",
                "aliases": [],
                "related": {},
                "senses": [
                    {
                        "definition": next(iter(context["references"].values()))[0]["definition"],
                        "pos": next(iter(context["references"])),
                        "references": ["a1"],
                    }
                ],
            }
        if target == "jetty":
            examples = [
                "Ships dock at the [jetty].",
                "SHIPS DOCK AT THE [JETTY].",
                "[jetty",
            ]
        else:
            examples = [
                f"The ship entered the [{target}] today ({n})."
                for n in range(context["examples_per_sense"])
            ]
        return {
            "senses": [
                {
                    "sense_id": sense["sense_id"],
                    "tier": "core",
                    "examples": examples,
                    "forms": [target],
                    "patterns": [],
                    "collocations": [],
                    "relations": {},
                    "cefr_level": "B1",
                    "register": None,
                }
                for sense in context["senses"]
            ]
        }


class BrowserCompletion(Completion):
    """Only the inference boundary is deterministic; native agents/tools stay real."""

    @staticmethod
    def last_message(messages):
        return next(
            m
            for m in reversed(messages)
            if not (
                m.type == "human"
                and isinstance(m.content, str)
                and m.content.startswith("<context>")
            )
        )

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = self.last_message(messages)
        content = last.content if isinstance(last.content, str) else "E2E vision"
        if "E2E fail" in content:
            raise RuntimeError("deterministic provider failure")
        if not isinstance(last, ToolMessage) and content == "E2E missing sense":
            result = answer(
                "",
                tool_calls=[
                    {
                        "name": "read_vocabulary",
                        "args": {"sense_ids": [999999]},
                        "id": "call_" + uuid4().hex,
                    }
                ],
            )
        elif isinstance(last, ToolMessage) and last.name == "read_vocabulary":
            assert last.status == "error" and last.content == "sense_not_found"
            result = answer("E2E recovered from a missing sense.")
        elif not isinstance(last, ToolMessage) and content.startswith("E2E create deck "):
            result = answer(
                "",
                tool_calls=[
                    {
                        "name": "create_node",
                        "args": {"type": "DECK", "name": content[16:]},
                        "id": "call_" + uuid4().hex,
                    }
                ],
            )
        elif not isinstance(last, ToolMessage) and content.startswith("E2E read node "):
            result = answer(
                "",
                tool_calls=[
                    {
                        "name": "read_library",
                        "args": {"node_id": content[14:]},
                        "id": "call_" + uuid4().hex,
                    }
                ],
            )
        elif isinstance(last, ToolMessage) and last.name == "read_library":
            result = answer("E2E tool result: " + str(last.content))
        else:
            result = answer("E2E response saved through the native checkpoint.")
        return self._result(result)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if self.last_message(messages).content == "E2E streaming across timeouts":
            from langchain_core.messages import AIMessageChunk
            from langchain_core.outputs import ChatGenerationChunk

            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[
                        {
                            "type": "reasoning",
                            "reasoning": "E2E reasoning arrives before the answer.",
                            "index": 0,
                        }
                    ]
                )
            )
            await asyncio.sleep(3)
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[{"type": "text", "text": "E2E first paragraph. ", "index": 1}]
                )
            )
            await asyncio.sleep(32)
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[{"type": "text", "text": "A long continuation. " * 200, "index": 1}]
                )
            )
            await asyncio.sleep(32)
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=[{"type": "text", "text": "E2E final paragraph.", "index": 1}],
                    usage_metadata={
                        "input_tokens": 10,
                        "output_tokens": 1000,
                        "total_tokens": 1010,
                    },
                )
            )
            return
        if self.last_message(messages).content == "E2E slow":
            await asyncio.sleep(3)
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield chunk

    def _result(self, message: AIMessage):
        from langchain_core.outputs import ChatGeneration, ChatResult

        return ChatResult(generations=[ChatGeneration(message=message)])


class DiagnosticProvider:
    async def decide(self, state, questions, **options):
        return SimpleNamespace(
            choices={
                name: SimpleNamespace(choice="no_candidate")
                for name, question in questions.items()
                if isinstance(question, Choice)
            },
            nouls={
                name: SimpleNamespace(noul=0.1)
                for name in questions
                if name in {"task_fit", "spelling_error", "used"}
            },
        )

    async def close(self):
        pass


async def test_full_stack(
    database, dictionary, deployment, config, monkeypatch, tmp_path, reference
):
    config = config.model_copy(
        update={
            "library": config.library.model_copy(
                update={
                    "max_children_per_folder": 16,
                    "max_senses_per_deck": 120,
                    "max_owned_nodes": 80,
                }
            )
        }
    )
    env_file = Path(os.environ.get("E2E_CLERK_ENV_FILE", ROOT / ".env"))
    keys = dotenv_values(env_file)
    provider_profile = os.environ.get("E2E_PROVIDER_PROFILE", "deterministic")
    assert provider_profile in {"deterministic", "live"}
    provider_environment = {
        field: os.environ.get(variable) or keys.get(variable)
        for field, variable in {
            "inference_api_key": "INFERENCE_API_KEY",
            "inference_base_url": "INFERENCE_BASE_URL",
            "decision_api_key": "LEXI_DECISION_API_KEY",
            "decision_base_url": "LEXI_DECISION_BASE_URL",
        }.items()
    }
    if provider_profile == "live":
        if not all(provider_environment.values()):
            pytest.fail(
                "Live provider smoke requires INFERENCE_API_KEY/BASE_URL and "
                "LEXI_DECISION_API_KEY/BASE_URL in the runner environment."
            )
    secret = os.environ.get("CLERK_SECRET_KEY") or keys.get("CLERK_SECRET_KEY", "")
    frontend = dotenv_values(ROOT / "apps/web/.env.local")
    public = (
        os.environ.get("CLERK_PUBLISHABLE_KEY")
        or keys.get("CLERK_PUBLISHABLE_KEY")
        or frontend.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "")
    )
    if not secret.startswith("sk_test_") or not public.startswith("pk_test_"):
        pytest.fail("Use a Clerk development instance.")
    assert frontend.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY") == public, (
        "FE and runner must use the same Clerk instance."
    )
    assert frontend.get("NEXT_PUBLIC_DATA_MODE") == "live", "The actual FE must run in live mode."
    base_url = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:3000")
    endpoint = socket.socket()
    endpoint.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        endpoint.bind(("127.0.0.1", 8000))
    except OSError:
        endpoint.close()
        pytest.fail(
            "Port 8000 already has an owner; do not start a second API or use its database."
        )
    endpoint.listen(128)
    endpoint.setblocking(False)
    ledger = tmp_path / "clerk-users.txt"
    ledger.touch(mode=0o600)
    run_env = dict(os.environ) | {
        "E2E_BASE_URL": base_url,
        "E2E_WORD_QUERY": "bank",
        "CLERK_SECRET_KEY": secret,
        "CLERK_PUBLISHABLE_KEY": public,
        "E2E_ACCOUNT_LEDGER": str(ledger),
        "E2E_RUN_ID": uuid4().hex[:12],
        "E2E_PROVIDER_PROFILE": provider_profile,
    }
    owned_users = []
    account_ids = {}
    child = None
    server = None
    serving = None
    async with (
        httpx.AsyncClient(
            base_url="https://api.clerk.com/v1/",
            headers={"Authorization": "Bearer " + secret},
            timeout=30,
        ) as clerk,
        AsyncExitStack() as stack,
    ):
        try:
            async with httpx.AsyncClient(timeout=10) as check:
                assert (await check.get(base_url + "/login")).status_code == 200, (
                    "Start the existing live Next frontend."
                )
            for account, plan in [("A", Plan.FREE), ("B", Plan.PRO), ("C", Plan.FREE)]:
                email = f"pycil-{run_env['E2E_RUN_ID']}-{account.lower()}+clerk_test@example.com"
                password = secrets.token_urlsafe(24) + "Aa1!"
                created = await clerk.post(
                    "users", json={"email_address": [email], "password": password}
                )
                assert created.status_code == 200, (
                    f"Clerk test-user creation failed: HTTP {created.status_code}"
                )
                identifier = created.json()["id"]
                owned_users.append(identifier)
                run_env[f"E2E_EMAIL_{account}"] = email
                run_env[f"E2E_PASSWORD_{account}"] = password
                _, sessions, _ = database
                async with sessions() as session, session.begin():
                    user = User(
                        clerk_subject=identifier,
                        settings={},
                        plan=plan,
                        cycle_anchor=datetime.now(UTC),
                    )
                    session.add(user)
                    await session.flush()
                    await provision_library(session, user.id)
                    account_ids[account] = user.id
                if account == "C":
                    async with sessions() as session:
                        await settle(
                            session,
                            user.id,
                            config,
                            execution_key=uuid4(),
                            feature=Feature.ASSISTANT,
                            units=config.plans[plan].monthly_allowance_units,
                            unmetered_calls=0,
                            moment=datetime.now(UTC),
                        )
            engine, _, _ = database
            with sqlite3.connect(reference) as connection:
                for identifier, lemma, definition in [
                    (2, "harbor", "a sheltered place for ships"),
                    (3, "quay", "a platform where ships load and unload"),
                    (4, "jetty", "a structure where boats can dock"),
                ]:
                    connection.execute(
                        "INSERT INTO words VALUES(?,?,?,?,?)",
                        (identifier, lemma, lemma, "word", "done"),
                    )
                    connection.execute(
                        "INSERT INTO entries(id,word_id,pos,definition,examples,entry_order) "
                        "VALUES(?,?,'noun',?,'[]',1)",
                        (identifier, identifier, definition),
                    )
                    connection.execute(
                        "INSERT INTO senses(id,entry_id,definition,sense_order) VALUES(?,?,?,1)",
                        (identifier, identifier, definition),
                    )
                connection.execute(
                    "INSERT INTO words VALUES(5,'glistening','glistening','word','done')"
                )
                connection.execute(
                    "INSERT INTO entries(id,word_id,pos,headword,definition,examples,entry_order) "
                    "VALUES(5,5,'verb','glisten','shine with reflected light','[]',1)"
                )
                connection.execute(
                    "INSERT INTO senses(id,entry_id,definition,sense_order) "
                    "VALUES(5,5,'shine with reflected light',1)"
                )
                connection.execute(
                    "INSERT INTO words VALUES(7,'glistened','glistened','word','done')"
                )
                connection.execute(
                    "INSERT INTO entries(id,word_id,pos,headword,definition,examples,entry_order) "
                    "VALUES(7,7,'verb','glisten','shine with reflected light','[]',1)"
                )
                connection.execute(
                    "INSERT INTO senses(id,entry_id,definition,sense_order) "
                    "VALUES(7,7,'shine with reflected light',1)"
                )
                connection.execute(
                    "INSERT INTO words VALUES(?,?,?,?,?)",
                    (6, "glisten-with", "glisten with something", "expression", "done"),
                )
                connection.execute(
                    "INSERT INTO entries(id,word_id,pos,headword,definition,examples,entry_order) "
                    "VALUES(6,6,'verb',?,?,'[]',1)",
                    ("glisten with something", "be covered with something shiny"),
                )
                connection.execute(
                    "INSERT INTO senses(id,entry_id,definition,sense_order) "
                    "VALUES(6,6,'be covered with something shiny',1)"
                )
            dictionary[0].llm = BrowserLexicalCompletion()
            await dictionary[0].import_reference(reference)
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO lexi.senses(id,word_id,pos,tier) SELECT n,1,'NOUN','CORE' "
                        "FROM generate_series(3,32) n"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.definitions(sense_id,content) "
                        "SELECT n,'a financial institution, fixture meaning ' || n "
                        "FROM generate_series(3,32) n"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.words(id,lemma,match_key,entry_type,generation_state) "
                        "VALUES(2,'archive','archive','WORD','DONE')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.senses(id,word_id,pos,tier) SELECT n,2,'NOUN','CORE' "
                        "FROM generate_series(100,200) n"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.definitions(sense_id,content) "
                        "SELECT n,'a collection of records, fixture meaning ' || n "
                        "FROM generate_series(100,200) n"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.examples(sense_id,content) "
                        "SELECT id,'I visited the [bank].' "
                        "FROM lexi.senses WHERE word_id=1"
                    )
                )
                for table in ("words", "senses"):
                    await connection.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('lexi.{table}','id'), "
                            f"(SELECT max(id) FROM lexi.{table}))"
                        )
                    )
            await fill(database, dictionary, config)
            async with sessions() as session, session.begin():
                moment = datetime.now(UTC) - timedelta(days=30)
                stability, difficulty, due = next_state(None, [1], moment, config)
                assert due < datetime.now(UTC)
                session.add(
                    UserSense(
                        user_id=account_ids["A"],
                        sense_id=30,
                        stability=stability,
                        difficulty=difficulty,
                        last_exposure_at=moment,
                        due_at=due,
                        elo=600,
                        review_count=1,
                        lapse_count=0,
                    )
                )
            dictionary[0].decision_model = DiagnosticProvider()
            real_deployment = deployment.model_copy(
                update={
                    "clerk_secret_key": SecretStr(secret),
                    "clerk_issuer": keys["CLERK_ISSUER"],
                    "clerk_jwks_url": keys["CLERK_JWKS_URL"],
                    "clerk_audience": keys.get("CLERK_AUDIENCE") or None,
                    "allowed_origins": [base_url],
                }
            )
            if provider_profile == "live":
                real_deployment = real_deployment.model_copy(
                    update={
                        key: SecretStr(value) if key.endswith("_key") else value
                        for key, value in provider_environment.items()
                    }
                )
            else:
                monkeypatch.setattr(agents, "model", lambda *args: nullcontext(BrowserCompletion()))
            real_deployment.validate_addresses()
            resources = await stack.enter_async_context(process_resources(config, real_deployment))
            if provider_profile != "live":
                resources.lexicon = dictionary[0]
                await resources.lexicon.start()
                resources.generations = dictionary[0].test_generations
            else:

                def observe(native):
                    async def observed(*args, **kwargs):
                        try:
                            return await native(*args, **kwargs)
                        except Exception as error:
                            detail = str(error.__cause__ or error)
                            if isinstance(error, ValidationError):
                                for issue in error.errors(include_context=False, include_url=False):
                                    value = issue.get("input")
                                    if isinstance(value, dict) and "examples" in value:
                                        detail += " | examples: " + json.dumps(
                                            value["examples"][:2]
                                        )
                                        break
                            trace = error.__traceback__
                            while trace:
                                frame = trace.tb_frame
                                if (
                                    frame.f_code.co_name == "validate_batch"
                                    and "question" in frame.f_locals
                                ):
                                    detail += " | item: " + json.dumps(
                                        frame.f_locals["question"].model_dump()
                                    )
                                    break
                                trace = trace.tb_next
                            for value in provider_environment.values():
                                detail = detail.replace(value, "[redacted]")
                            print(
                                f"Native {native.__name__} error "
                                f"({type(error).__name__}): {detail[:1000]}",
                                flush=True,
                            )
                            raise

                    return observed

                for operation in ("generate_word", "generate_question_artifacts"):
                    monkeypatch.setattr(
                        resources.lexicon, operation, observe(getattr(resources.lexicon, operation))
                    )
                from openai.resources.chat.completions import AsyncCompletions

                monkeypatch.setattr(AsyncCompletions, "parse", observe(AsyncCompletions.parse))
            app = create_app()
            app.state.product, app.state.deployment = config, real_deployment
            app.state.identity = Identity(real_deployment)
            for name, value in vars(resources).items():
                setattr(app.state, name, value)
            server = uvicorn.Server(
                uvicorn.Config(app, lifespan="off", access_log=False, log_level="warning")
            )
            serving = asyncio.create_task(server.serve(sockets=[endpoint]))

            for _ in range(100):
                if server.started:
                    break
                await asyncio.sleep(0.05)
            assert server.started, "The owned API failed to start."
            args = [
                "pnpm",
                "run",
                "test:e2e",
            ]
            if provider_profile == "live":
                args += ["provider.spec.ts"]
            if os.environ.get("E2E_GREP"):
                args += ["--grep", os.environ["E2E_GREP"]]
            child = await asyncio.create_subprocess_exec(
                *args, cwd=ROOT / "apps/web", env=run_env, start_new_session=True
            )
            status = await child.wait()
            assert status == 0, (
                "Playwright full-stack tests failed; inspect the private e2e report."
            )
        finally:
            cleanup = []
            if child and child.returncode is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    await asyncio.wait_for(child.wait(), 10)
                except TimeoutError:
                    os.killpg(child.pid, signal.SIGKILL)
                    await child.wait()
            if server is not None:
                server.should_exit = True
            if serving:
                try:
                    await asyncio.wait_for(serving, 15)
                except Exception:
                    cleanup.append("The owned API did not stop cleanly.")
            endpoint.close()
            for email in ledger.read_text().splitlines():
                assert (
                    email.startswith(f"pycil-{run_env['E2E_RUN_ID']}-") and "+clerk_test@" in email
                )
                try:
                    found = await clerk.get("users", params={"email_address": email})
                except httpx.HTTPError:
                    cleanup.append("Could not resolve an owned test signup.")
                    continue
                if found.status_code == 200:
                    owned_users.extend(item["id"] for item in found.json())
                else:
                    cleanup.append("Could not resolve an owned test signup.")
            for identifier in set(owned_users):
                try:
                    deleted = await clerk.delete("users/" + identifier)
                except httpx.HTTPError:
                    cleanup.append("Could not delete an owned Clerk test user.")
                    continue
                if deleted.status_code not in {200, 204, 404}:
                    cleanup.append("Could not delete an owned Clerk test user.")
            assert not cleanup, cleanup
