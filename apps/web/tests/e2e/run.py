"""Own a disposable actual-stack E2E run, including exact Clerk/user cleanup."""

import argparse
import asyncio
import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
import yaml
from pycil.app.config import load_config
from pycil.app.migrate import migrate
from pycil.infrastructure.database import connect
from sqlalchemy.engine import make_url
from support.data import seed
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

SUPPORT = Path(__file__).parent / "support"

ROOT = Path(__file__).resolve().parents[4]
WEB = ROOT / "apps/web"
API = ROOT / "apps/api"


def environment():
    values = {}
    for path in [
        ROOT / ".env",
        WEB / ".env.local",
        Path(os.environ["E2E_CLERK_ENV_FILE"]) if os.environ.get("E2E_CLERK_ENV_FILE") else None,
    ]:
        if path is None or not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.removeprefix("export ").partition("=")
            if separator:
                parsed = shlex.split(value, comments=True)
                values[key.strip()] = parsed[0] if parsed else ""
    values.update(os.environ)
    values["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"] = values.get("CLERK_PUBLISHABLE_KEY") or values.get(
        "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", ""
    )
    return values


def free_port(port):
    with socket.socket() as connection:
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            connection.bind(("127.0.0.1", port))
        except OSError:
            raise RuntimeError(f"Owned E2E port {port} is occupied") from None


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def start(stack, command, cwd, env, log):
    output = stack.enter_context(log.open("w"))
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=output,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    stack.callback(stop, process)
    return process


def ready(process, url, log):
    until = time.monotonic() + 120
    with httpx.Client() as client:
        while time.monotonic() < until:
            if process.poll() is not None:
                raise RuntimeError(f"Process exited before readiness; see {log}")
            try:
                if client.get(url, timeout=2).is_success:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
    raise RuntimeError(f"Readiness timed out: {url}; see {log}")


async def initialize(url, identities, config):
    engine, sessions = connect(url)
    try:
        await seed(sessions, identities, config)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args, playwright_args = parser.parse_known_args()
    if playwright_args[:1] == ["--"]:
        playwright_args = playwright_args[1:]
    env = environment()
    required = [
        "CLERK_SECRET_KEY",
        "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
        "CLERK_ISSUER",
        "CLERK_JWKS_URL",
    ]
    if args.live:
        required += [
            "LLM_API_KEY",
            "LLM_BASE_URL",
            "DECISION_API_KEY",
            "DECISION_BASE_URL",
        ]
    missing = [name for name in required if not env.get(name)]
    if missing:
        raise RuntimeError("Missing E2E credentials: " + ", ".join(missing))
    if not env["CLERK_SECRET_KEY"].startswith("sk_test_"):
        raise RuntimeError("E2E requires a Clerk development instance")
    for port in [8100, 3200, *([] if args.live else [8110])]:
        free_port(port)
    report = WEB / "test-results" / ("live-stack" if args.live else "default-stack")
    report.mkdir(parents=True, exist_ok=True)
    run_id = secrets.token_hex(6)
    env["E2E_RUN_ID"] = run_id
    env["E2E_PROVIDER_PROFILE"] = "live" if args.live else "default"
    env["E2E_BASE_URL"] = "http://localhost:3200"
    env["NEXT_PUBLIC_DATA_MODE"] = "live"
    env["PYCIL_API_URL"] = env["NEXT_PUBLIC_PYCIL_API_URL"] = "http://127.0.0.1:8100"
    env["ALLOWED_ORIGINS"] = "http://localhost:3200,http://127.0.0.1:3200"
    with ExitStack() as stack:
        temporary = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="pycil-e2e-")))
        ledger = temporary / "accounts.txt"
        ledger.touch(mode=0o600)
        env["E2E_ACCOUNT_LEDGER"] = str(ledger)
        clerk = stack.enter_context(
            httpx.Client(
                base_url="https://api.clerk.com/v1/",
                headers={"Authorization": "Bearer " + env["CLERK_SECRET_KEY"]},
                timeout=30,
            )
        )
        identities = {}
        cleanup_ids = set()

        def cleanup_users():
            failures = []
            # Signup tests record their exact owned emails before creating an identity.
            for email in ledger.read_text().splitlines():
                try:
                    response = clerk.get("users", params={"email_address": email})
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    failures.append(type(error).__name__)
                    continue
                cleanup_ids.update(
                    item["id"]
                    for item in response.json()
                    if any(address["email_address"] == email for address in item["email_addresses"])
                )
            for identifier in cleanup_ids:
                try:
                    response = clerk.delete("users/" + identifier)
                except httpx.HTTPError as error:
                    failures.append(type(error).__name__)
                    continue
                if response.status_code not in {200, 404}:
                    failures.append(response.status_code)
            if failures:
                raise RuntimeError(f"Clerk cleanup failed: {failures}")

        stack.callback(cleanup_users)
        for label in ["A", "B", "C"]:
            email = f"pycil-{run_id}-{label.lower()}+clerk_test@example.com"
            password = secrets.token_urlsafe(24) + "!aA7"
            response = clerk.post("users", json={"email_address": [email], "password": password})
            if not response.is_success:
                raise RuntimeError(f"Clerk fixture creation failed: HTTP {response.status_code}")
            identifier = response.json()["id"]
            cleanup_ids.add(identifier)
            identities[label] = identifier
            env["E2E_EMAIL_" + label] = email
            env["E2E_PASSWORD_" + label] = password
        print("Created three temporary Clerk development identities.", flush=True)
        postgres = stack.enter_context(PostgresContainer("postgres:18.6", driver="psycopg"))
        redis = stack.enter_context(RedisContainer("redis:8.10.2-alpine3.23"))
        url = (
            make_url(postgres.get_connection_url())
            .set(drivername="postgresql+asyncpg")
            .render_as_string(hide_password=False)
        )
        env["DB_URL"] = url
        env["REDIS_URL"] = (
            f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"
        )
        # Import genuine reference rows only for words exercised by the browser suites.
        reference = temporary / "reference.jsonl"
        targets = {
            "bank",
            "harbor",
            "harbour",
            "quay",
            "jetty",
            "glisten",
            "glisten-with",
            "glistened",
            "glistening",
        }
        with (
            reference.open("w") as output,
            (ROOT / "data/reference.jsonl").open() as source,
        ):
            for line in source:
                item = json.loads(line)
                if item["lemma"] in targets or item["lemma"].startswith("glisten with"):
                    output.write(line)
        migrate(url, reference_path=reference)
        config = load_config()
        asyncio.run(initialize(url, identities, config))
        policy = yaml.safe_load((ROOT / "config/config.yaml").read_text())
        if not args.live:
            env.update(
                LLM_API_KEY="controlled-e2e",
                LLM_BASE_URL="http://127.0.0.1:8110",
                DECISION_API_KEY="controlled-e2e",
                DECISION_BASE_URL="http://127.0.0.1:8110/decisions",
            )
            provider = start(
                stack,
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "provider:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8110",
                ],
                SUPPORT,
                env,
                report / "provider.log",
            )
            ready(provider, "http://127.0.0.1:8110/health", report / "provider.log")
        config_path = temporary / "config.yaml"
        config_path.write_text(yaml.safe_dump(policy))
        env["CONFIG_PATH"] = str(config_path)
        api = start(
            stack,
            [
                sys.executable,
                "-m",
                "uvicorn",
                "pycil.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8100",
            ],
            API,
            env,
            report / "api.log",
        )
        ready(api, "http://127.0.0.1:8100/ready", report / "api.log")
        print("Disposable API ready at :8100; building production frontend.", flush=True)
        snapshot = temporary / "web"
        shutil.copytree(
            WEB,
            snapshot,
            ignore=shutil.ignore_patterns(
                "node_modules",
                ".next",
                ".env*",
                "test-results",
                "playwright-report",
                "storybook-static",
                ".storybook",
            ),
        )
        shutil.copytree(WEB / "node_modules", snapshot / "node_modules", symlinks=True)
        build = start(stack, ["pnpm", "build"], snapshot, env, report / "build.log")
        if build.wait():
            raise RuntimeError(f"Production frontend build failed; see {report / 'build.log'}")
        web = start(
            stack,
            [
                "node",
                str(WEB / "node_modules/next/dist/bin/next"),
                "start",
                "--hostname",
                "localhost",
                "--port",
                "3200",
            ],
            snapshot,
            env,
            report / "web.log",
        )
        ready(web, env["E2E_BASE_URL"] + "/icon.svg", report / "web.log")
        command = [
            "pnpm",
            "exec",
            "playwright",
            "test",
            "--project=e2e",
            "--output",
            str(temporary / "browser-results"),
            *playwright_args,
        ]
        if env.get("E2E_GREP"):
            command += ["--grep", env["E2E_GREP"]]
        print(f"Running {env['E2E_PROVIDER_PROFILE']} E2E.", flush=True)
        browser = subprocess.Popen(command, cwd=WEB, env=env, start_new_session=True)
        stack.callback(stop, browser)
        result = browser.wait()
        shutil.rmtree(report / "browser", ignore_errors=True)
        shutil.copytree(temporary / "browser-results", report / "browser")
        return result


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Never include SDK exception text; it can contain credentials/request payloads.
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        else:
            print(f"E2E setup/cleanup failed: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
