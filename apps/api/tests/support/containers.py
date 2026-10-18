import contextlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from filelock import FileLock
from psycopg import sql
from redis.asyncio import Redis
from sqlalchemy.engine import make_url
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer
from testcontainers.core.docker_client import DockerClient

from pycil.app.migrate import migrate
from pycil.infrastructure.database import connect


class PostgresProxy:
    def __init__(self, connection_url: str):
        self._url = connection_url

    def get_connection_url(self) -> str:
        return self._url


class RedisProxy:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = int(port)

    def get_container_host_ip(self) -> str:
        return self._host

    def get_exposed_port(self, port: int = 6379) -> int:
        return self._port


def _stop_container_by_id(container_id: str | None):
    if not container_id:
        return
    try:
        client = DockerClient()
        c = client.client.containers.get(container_id)
        c.stop(timeout=2)
        c.remove(v=True, force=True)
    except Exception:
        pass


def _init_template_db(connection_url: str):
    address = make_url(connection_url)
    admin_url = address.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'pycil_template'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE pycil_template")
            template_url = address.set(
                drivername="postgresql+asyncpg", database="pycil_template"
            ).render_as_string(hide_password=False)
            migrate(template_url)
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = 'pycil_template' AND pid <> pg_backend_pid()"
            )
            conn.execute(
                "ALTER DATABASE pycil_template WITH is_template true allow_connections false"
            )


def _read_workers(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


@pytest.fixture(scope="session")
def postgres(tmp_path_factory, worker_id):
    if worker_id == "master":
        container = PostgresContainer("postgres:18.6", driver="psycopg")
        container.with_command("-c fsync=off -c synchronous_commit=off -c full_page_writes=off")
        try:
            container.start()
            _init_template_db(container.get_connection_url())
            yield container
        finally:
            container.stop()
    else:
        os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"
        shared_dir = tmp_path_factory.getbasetemp().parent
        lock_path = shared_dir / "postgres.lock"
        meta_path = shared_dir / "postgres.json"
        workers_path = shared_dir / "postgres_workers.json"

        with FileLock(str(lock_path)):
            if not meta_path.exists():
                container = PostgresContainer("postgres:18.6", driver="psycopg")
                container.with_command(
                    "-c fsync=off -c synchronous_commit=off -c full_page_writes=off"
                )
                try:
                    container.start()
                    _init_template_db(container.get_connection_url())
                    cid = container._container.id
                    url = container.get_connection_url()
                    meta_path.write_text(json.dumps({"url": url, "container_id": cid}))
                    workers_path.write_text(json.dumps([worker_id]))
                except BaseException:
                    with contextlib.suppress(Exception):
                        container.stop()
                    raise
            else:
                meta = json.loads(meta_path.read_text())
                url = meta["url"]
                workers = _read_workers(workers_path)
                if worker_id not in workers:
                    workers.append(worker_id)
                    workers_path.write_text(json.dumps(workers))

        yield PostgresProxy(url)

        with FileLock(str(lock_path)):
            workers = _read_workers(workers_path)
            if worker_id in workers:
                workers.remove(worker_id)
                workers_path.write_text(json.dumps(workers))

            if not workers:
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                        _stop_container_by_id(meta.get("container_id"))
                    except Exception:
                        pass
                    meta_path.unlink(missing_ok=True)
                workers_path.unlink(missing_ok=True)


@pytest.fixture
async def database(postgres):
    name = "test_" + uuid4().hex
    address = make_url(postgres.get_connection_url())
    admin_url = address.set(drivername="postgresql").render_as_string(hide_password=False)
    connection = await psycopg.AsyncConnection.connect(admin_url, autocommit=True)
    async with connection:
        await connection.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE pycil_template").format(sql.Identifier(name))
        )
    engine = None
    try:
        url = address.set(drivername="postgresql+asyncpg", database=name).render_as_string(
            hide_password=False
        )
        engine, sessions = connect(url)
        yield SimpleNamespace(url=url, engine=engine, sessions=sessions)
    finally:
        if engine is not None:
            await engine.dispose()
        connection = await psycopg.AsyncConnection.connect(admin_url, autocommit=True)
        async with connection:
            await connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture(scope="session")
def redis_container(tmp_path_factory, worker_id):
    if worker_id == "master":
        container = RedisContainer("redis:8.10.2-alpine3.23")
        try:
            container.start()
            yield container
        finally:
            container.stop()
    else:
        os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"
        shared_dir = tmp_path_factory.getbasetemp().parent
        lock_path = shared_dir / "redis.lock"
        meta_path = shared_dir / "redis.json"
        workers_path = shared_dir / "redis_workers.json"

        with FileLock(str(lock_path)):
            if not meta_path.exists():
                container = RedisContainer("redis:8.10.2-alpine3.23")
                try:
                    container.start()
                    cid = container._container.id
                    host = container.get_container_host_ip()
                    port = int(container.get_exposed_port(6379))
                    meta_path.write_text(
                        json.dumps({"host": host, "port": port, "container_id": cid})
                    )
                    workers_path.write_text(json.dumps([worker_id]))
                except BaseException:
                    with contextlib.suppress(Exception):
                        container.stop()
                    raise
            else:
                meta = json.loads(meta_path.read_text())
                host = meta["host"]
                port = meta["port"]
                workers = _read_workers(workers_path)
                if worker_id not in workers:
                    workers.append(worker_id)
                    workers_path.write_text(json.dumps(workers))

        yield RedisProxy(host, port)

        with FileLock(str(lock_path)):
            workers = _read_workers(workers_path)
            if worker_id in workers:
                workers.remove(worker_id)
                workers_path.write_text(json.dumps(workers))

            if not workers:
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                        _stop_container_by_id(meta.get("container_id"))
                    except Exception:
                        pass
                    meta_path.unlink(missing_ok=True)
                workers_path.unlink(missing_ok=True)


@pytest.fixture
async def redis_store(redis_container):
    client = Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    namespace = "test:" + uuid4().hex
    try:
        yield client, namespace
    finally:
        keys = [key async for key in client.scan_iter(match=namespace + "*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        return
    try:
        if not hasattr(session.config, "_tmp_path_factory"):
            return
        basetemp = session.config._tmp_path_factory.getbasetemp()
        for name in ("postgres", "redis"):
            meta_path = basetemp / f"{name}.json"
            workers_path = basetemp / f"{name}_workers.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    _stop_container_by_id(meta.get("container_id"))
                except Exception:
                    pass
                meta_path.unlink(missing_ok=True)
            workers_path.unlink(missing_ok=True)
    except Exception:
        pass
