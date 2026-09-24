"""A running Pycil stack for system-level tests.

System tests talk to a real API and a real worker over HTTP, so this module's whole
job is to bring those up against disposable stores and to take them down again.
Nothing here fakes Pycil behaviour: PostgreSQL, Redis and the job stream are real
services, and the two substitutions are both at a network boundary the deployment
also crosses — Clerk's JWKS and the LLM provider.

Two things make it usable rather than merely correct:

- **Ephemeral ports, not fixed ones.** Containers and the API take a free port from
  the OS, so two runs — or two worktrees — cannot collide, and there is no stale
  owner to hunt down before starting. The failure a fixed port produces is an
  "address already in use" that says nothing about which process holds it.
- **One stack per session, isolation per test.** Starting Postgres, a worker and a
  migration pass costs seconds; doing it per test would put the suite past the point
  where anyone runs it. Tests isolate by unique Clerk subjects and a table reset,
  not by a fresh cluster.

The worker is launched through `taskiq worker`, the same entrypoint the container
image uses. Calling `broker.startup()` directly looks equivalent and is not: it
skips the receiver, so nothing consumes the stream and the API's readiness probe
never sees a heartbeat.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
API_DIR = REPO / "apps" / "api"
WORKER_DIR = REPO / "apps" / "worker"

_POSTGRES_IMAGE = "postgres:16-alpine"
_REDIS_IMAGE = "redis:7-alpine"

#: How long a starting API or worker may take before the stack is declared broken.
#: Generous because the first `uv run` in a cold cache resolves the environment.
_STARTUP_TIMEOUT_SECONDS = 180.0


class StackUnavailable(RuntimeError):
    """The stack could not be started, with a message that says which part."""


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_for_http(url: str, *, timeout: float, process: subprocess.Popen | None = None) -> None:
    """Poll until the URL answers, failing early if the process it belongs to died."""
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise StackUnavailable(f"process exited with {process.returncode}: {_output(process)}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 400:
                    return
        except urllib.error.HTTPError as exc:
            last = exc
        except OSError as exc:
            last = exc
        time.sleep(0.25)
    raise StackUnavailable(f"{url} did not become available: {last}")


def _output(process: subprocess.Popen) -> str:
    """Whatever the process printed, for the failure message."""
    if process.stdout is None:
        return ""
    process.stdout.flush()
    try:
        return os.read(process.stdout.fileno(), 8192).decode(errors="replace")
    except OSError:
        return ""


@dataclass(frozen=True)
class Stores:
    """The disposable database and Redis the stack runs against."""

    database_url: str
    redis_url: str

    @property
    def sync_database_url(self) -> str:
        """The psycopg/asyncpg-neutral URL the migration and reset helpers use."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class SystemStack:
    """A live API + worker + stores, addressed over HTTP."""

    def __init__(self, *, stores: Stores, api_port: int, env: dict[str, str]) -> None:
        self.stores = stores
        self.api_port = api_port
        self.env = env
        self._api: subprocess.Popen | None = None
        self._worker: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    def start(self) -> SystemStack:
        self._migrate()
        self._worker = self._spawn(
            ["uv", "run", "taskiq", "worker", "pycil_worker.main:broker", "--workers", "1"],
            cwd=WORKER_DIR,
        )
        self._api = self._spawn(
            [
                "uv", "run", "uvicorn", "pycil.main:app",
                "--host", "127.0.0.1", "--port", str(self.api_port), "--log-level", "warning",
            ],
            cwd=API_DIR,
        )
        _wait_for_http(
            f"{self.base_url}/health/live", timeout=_STARTUP_TIMEOUT_SECONDS, process=self._api
        )
        # Readiness is the worker's signal: it stays 503 until a heartbeat appears,
        # so waiting here is what makes "the stack is up" mean jobs can run.
        _wait_for_http(
            f"{self.base_url}/health/ready", timeout=_STARTUP_TIMEOUT_SECONDS, process=self._api
        )
        return self

    def stop(self) -> None:
        """Stop both processes and their children, escalating only if one ignores it."""
        for process in (self._api, self._worker):
            if process is not None:
                self._signal_group(process, signal.SIGTERM)
        for process in (self._api, self._worker):
            if process is None:
                continue
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self._signal_group(process, signal.SIGKILL)
                process.wait(timeout=10)

    def kill_worker(self) -> None:
        """Kill the *test's own* worker, for the crash-recovery journeys.

        Deliberately not ``pkill`` or a pattern match: a broad pattern would reach a
        worker the developer is running by hand, and the only process a journey is
        entitled to kill is the one this stack started. The signal goes to the
        worker's whole process group, because ``uv run`` is a wrapper and signalling
        only it would leave the real consumer running.

        The API is left up, which is what makes the recovery observable: the receipt a
        client is polling must reach a terminal state even though the process that
        owned the work is gone.
        """
        if self._worker is None or self._worker.poll() is not None:
            raise StackUnavailable("the stack's worker is not running")
        self._signal_group(self._worker, signal.SIGKILL)
        self._worker.wait(timeout=20)

    def start_worker(self) -> None:
        """Start a replacement worker after :meth:`kill_worker`.

        A new process rather than a restart of the old one: the point of the crash
        journey is that work survives a *lost* worker, so recovery has to come from a
        process that never saw the original in-memory state.
        """
        self._worker = self._spawn(
            ["uv", "run", "taskiq", "worker", "pycil_worker.main:broker", "--workers", "1"],
            cwd=WORKER_DIR,
        )
        _wait_for_http(
            f"{self.base_url}/health/ready", timeout=_STARTUP_TIMEOUT_SECONDS, process=self._api
        )

    def _spawn(self, argv: list[str], *, cwd: Path) -> subprocess.Popen:
        """Start one stack process in its own session.

        ``start_new_session`` puts the process in a new process group, which is what
        makes :meth:`_signal_group` able to stop the *whole* command. It matters
        because the stack runs through ``uv run``, which spawns the real server as a
        child: signalling only the wrapper leaves uvicorn or taskiq alive, holding its
        port and still consuming the job stream. That is not a subtle failure — it
        looks like the harness working while the process it supposedly stopped keeps
        running.
        """
        return subprocess.Popen(
            argv,
            cwd=cwd,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

    @staticmethod
    def _signal_group(process: subprocess.Popen, signal_number: int) -> None:
        """Signal a spawned process and every child it started."""
        if process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal_number)
        except (ProcessLookupError, PermissionError):
            # Already gone, or the group is not ours to signal; fall back to the
            # direct pid so a normal stop still happens.
            with suppress(ProcessLookupError):
                process.send_signal(signal_number)

    def _migrate(self) -> None:
        """Bring both schemas to head. Lexi first: Pycil's content tables reference it."""
        lexi_ini = subprocess.run(
            [
                "uv", "run", "python", "-c",
                "import pathlib, lexi_ai.migrations;"
                " print(pathlib.Path(lexi_ai.migrations.__file__).parent / 'alembic.ini')",
            ],
            cwd=API_DIR, env=self.env, capture_output=True, text=True, check=True,
        ).stdout.strip()
        for argv in (
            ["uv", "run", "alembic", "-c", lexi_ini, "upgrade", "head"],
            ["uv", "run", "alembic", "upgrade", "head"],
        ):
            result = subprocess.run(
                argv, cwd=API_DIR, env=self.env, capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                raise StackUnavailable(
                    f"migration failed: {' '.join(argv)}\n{result.stderr[-4000:]}"
                )


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, check=False, timeout=30
    )
    return probe.returncode == 0


def provision_stores() -> tuple[Stores, object]:
    """Disposable PostgreSQL and Redis, from CI when supplied, else from Docker."""
    configured = _configured_stores()
    if configured is not None:
        return configured, _NullLifecycle()

    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    postgres = PostgresContainer(_POSTGRES_IMAGE, driver="asyncpg")
    redis = RedisContainer(_REDIS_IMAGE)
    postgres.start()
    redis.start()
    stores = Stores(
        database_url=postgres.get_connection_url(),
        redis_url=f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
    )
    return stores, _Containers(postgres, redis)


def stores_available() -> bool:
    """Whether this machine can provide the stores a system test needs."""
    return docker_available() or _configured_stores() is not None


def _configured_stores() -> Stores | None:
    """CI provides services directly; a container inside the job would be a second one."""
    database_url = os.environ.get("TEST_STACK_DB_URL")
    redis_url = os.environ.get("TEST_STACK_REDIS_URL")
    if database_url and redis_url:
        return Stores(database_url=database_url, redis_url=redis_url)
    return None


class _Containers:
    def __init__(self, *containers: object) -> None:
        self._containers = containers

    def stop(self) -> None:
        for container in self._containers:
            container.stop()  # type: ignore[attr-defined]


class _NullLifecycle:
    def stop(self) -> None:
        """CI owns its services; there is nothing here to stop."""


def stack_env(stores: Stores, *, clerk_jwks_url: str, clerk_issuer: str,
              clerk_audience: str, llm_base_url: str) -> dict[str, str]:
    """Environment for the API and worker, with both external providers redirected.

    Clerk and the LLM provider are pointed at test-owned servers rather than at a
    live service. Everything else — the database, Redis, the job stream — is the
    real thing, so a test cannot pass by agreeing with a fake of Pycil's own code.
    """
    reference = reference_dataset_path()
    return os.environ | {
        "ENVIRONMENT": "development",
        "DB_URL": stores.database_url,
        "DATABASE_URL": stores.sync_database_url,
        "LEXI_DB_URL": stores.database_url,
        "LEXI_DB_SCHEMA": "lexi",
        "LEXI_CAMBRIDGE_DB_PATH": reference,
        "REDIS_URL": stores.redis_url,
        "INTERNAL_SECRET": "system-test-internal-secret-at-least-32-bytes",
        "ASSISTANT_CHECKPOINT_DB_URL": stores.database_url,
        "ASSISTANT_API_KEY": "system-test-key",
        "ASSISTANT_BASE_URL": llm_base_url,
        "LEXI_LLM_BASE_URL": llm_base_url,
        "LEXI_LLM_API_KEY": "system-test-key",
        "LEXI_LLM_MODEL": "system-test-model",
        "LEXI_LLM_STRUCTURED_METHOD": "function_calling",
        "CLERK_JWKS_URL": clerk_jwks_url,
        "CLERK_ISSUER": clerk_issuer,
        "CLERK_AUDIENCE": clerk_audience,
        "ALLOWED_ORIGINS": "http://127.0.0.1",
        "PYTHONUNBUFFERED": "1",
    }


def reference_dataset_path() -> str:
    """The Cambridge artifact dictionary reads come from.

    Read from the environment first, then from the repository `.env` — the path is a
    compose-level variable, so it lives there rather than in either app's settings,
    and a developer who ran `docker compose up` has it set for the containers but not
    for their shell.
    """
    configured = os.environ.get("LEXI_REFERENCE_DATASET_PATH")
    if configured:
        return configured
    env_file = REPO / ".env"
    if not env_file.is_file():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "LEXI_REFERENCE_DATASET_PATH":
            return value.strip().strip("'\"")
    return ""


def require_reference_dataset() -> str:
    """Fail with the actual problem when the artifact is missing.

    Without it the stack still starts, but every dictionary read returns nothing,
    which surfaces much later as a confusing assertion failure in an unrelated
    journey.
    """
    path = reference_dataset_path()
    if not path or not Path(path).is_file():
        raise StackUnavailable(
            "LEXI_REFERENCE_DATASET_PATH must point at the Cambridge reference artifact"
        )
    return path


def start_stack(*, clerk_jwks_url: str, clerk_issuer: str, clerk_audience: str,
                llm_base_url: str) -> tuple[SystemStack, object]:
    stores, lifecycle = provision_stores()
    env = stack_env(
        stores,
        clerk_jwks_url=clerk_jwks_url,
        clerk_issuer=clerk_issuer,
        clerk_audience=clerk_audience,
        llm_base_url=llm_base_url,
    )
    stack = SystemStack(stores=stores, api_port=_free_port(), env=env)
    try:
        stack.start()
    except Exception:
        stack.stop()
        lifecycle.stop()
        raise
    return stack, lifecycle


def python_executable() -> str:
    """The interpreter running the tests, for subprocesses that need the same deps."""
    return sys.executable


def iter_lines(process: subprocess.Popen) -> Iterator[str]:
    """Drain a child's output; used by failure diagnostics."""
    if process.stdout is None:
        return
    yield from process.stdout
