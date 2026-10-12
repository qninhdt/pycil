"""Opt-in real Clerk/browser suite; stores are owned by scripts/test_api.py."""

import asyncio
import json
import os
import secrets
import shutil
import socket
import sqlite3
import tempfile
from contextlib import AsyncExitStack, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import uvicorn
from dotenv import dotenv_values
from pydantic import SecretStr, ValidationError
from sqlalchemy import text

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
from tests.support.inference import BrowserCompletion, BrowserLexicalCompletion, DiagnosticProvider
from tests.support.web_e2e_data import fill

ROOT = Path(__file__).resolve().parents[4]


async def run_web_e2e(database, dictionary, deployment, config, monkeypatch, tmp_path, reference):
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
    assert (
        not frontend.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
        or frontend.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY") == public
    ), "FE and runner must use the same Clerk instance."
    identity_environment = {
        name: os.environ.get(name) or keys.get(name) for name in ("CLERK_ISSUER", "CLERK_JWKS_URL")
    }
    if not all(identity_environment.values()):
        pytest.fail("Set CLERK_ISSUER and CLERK_JWKS_URL for the Clerk development instance.")
    base_url = "http://localhost:3200"
    endpoint = socket.socket()
    endpoint.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        endpoint.bind(("127.0.0.1", 8100))
    except OSError:
        endpoint.close()
        pytest.fail("Port 8100 already has an owner; stop the owned E2E API before rerunning.")
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
        "NEXT_PUBLIC_DATA_MODE": "live",
        "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": public,
        "PYCIL_API_URL": "http://127.0.0.1:8100",
    }
    owned_users = []
    account_ids = {}
    child = None
    web_child = None
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
            web_root = ROOT / "apps/web"
            web_snapshot = Path(
                stack.enter_context(tempfile.TemporaryDirectory(prefix=".pycil-e2e-web-", dir=ROOT))
            )
            shutil.copytree(
                web_root,
                web_snapshot,
                dirs_exist_ok=True,
                symlinks=True,
                ignore=shutil.ignore_patterns(
                    "node_modules", ".next", ".env*", "test-results", "playwright-report"
                ),
            )
            shutil.copytree(
                web_root / "node_modules",
                web_snapshot / "node_modules",
                symlinks=True,
                copy_function=os.link,
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
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM lexi.question_artifacts WHERE sense_id IN (31,32)")
                )
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO lexi.senses(id,word_id,pos,tier) VALUES(33,1,'VERB','CORE')")
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.definitions(sense_id,content) VALUES(33,'to deposit"
                        " money in a financial institution')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.word_aliases(word_id,content,match_key)"
                        " VALUES(1,'bank-alt','bank-alt')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.sense_forms(sense_id,surface,match_key,head_key,inf)"
                        " VALUES(33,'banking','banking','banking','ING')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.sense_patterns(sense_id,content,head_key)"
                        " VALUES(33,'bank with {sb}','bank')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.collocations(sense_id,content) VALUES(33,'[bank] a"
                        " cheque')"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO lexi.word_relations(from_word_id,to_word_id,rel_type)"
                        " VALUES(1,2,'WORD_FAMILY')"
                    )
                )
                await connection.execute(
                    text(
                        "SELECT setval(pg_get_serial_sequence('lexi.senses','id'), (SELECT"
                        " max(id) FROM lexi.senses))"
                    )
                )
            dictionary[0].llm.question_failure = True
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
                    "clerk_issuer": identity_environment["CLERK_ISSUER"],
                    "clerk_jwks_url": identity_environment["CLERK_JWKS_URL"],
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
                "node",
                "node_modules/@playwright/test/cli.js",
                "test",
                "--config",
                "playwright.config.ts",
                "--project",
                "e2e",
            ]
            if provider_profile == "live":
                args += ["--grep", "@live-provider"]
            if os.environ.get("E2E_GREP"):
                args += ["--grep", os.environ["E2E_GREP"]]
            with socket.socket() as web_port:
                web_port.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    web_port.bind(("127.0.0.1", 3200))
                except OSError:
                    pytest.fail(
                        "Port 3200 already has an owner; stop the owned E2E frontend first."
                    )
            web_child = await asyncio.create_subprocess_exec(
                "node",
                "node_modules/next/dist/bin/next",
                "build",
                cwd=web_snapshot,
                env=run_env,
            )
            assert await web_child.wait() == 0, "The E2E production build failed."
            web_child = await asyncio.create_subprocess_exec(
                "node",
                "node_modules/next/dist/bin/next",
                "start",
                "--hostname",
                "localhost",
                "--port",
                "3200",
                cwd=web_snapshot,
                env=run_env,
            )
            async with httpx.AsyncClient(timeout=2) as check:
                for _ in range(120):
                    assert web_child.returncode is None, "The owned E2E frontend failed to start."
                    try:
                        if (await check.get(base_url + "/favicon.svg")).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.5)
                else:
                    pytest.fail("The owned E2E frontend failed readiness.")
            child = await asyncio.create_subprocess_exec(*args, cwd=ROOT / "apps/web", env=run_env)
            status = await child.wait()
            assert status == 0, (
                "Playwright full-stack tests failed; inspect the private e2e report."
            )
        finally:
            cleanup = []
            if child and child.returncode is None:
                child.terminate()
                try:
                    await asyncio.wait_for(child.wait(), 10)
                except TimeoutError:
                    child.kill()
                    await child.wait()
            if web_child and web_child.returncode is None:
                web_child.terminate()
                try:
                    await asyncio.wait_for(web_child.wait(), 10)
                except TimeoutError:
                    web_child.kill()
                    await web_child.wait()
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
