"""One lock-owning worker; explicit generation and assistant retention calls."""

import argparse
import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import text

from pycil.config import Deployment, load_config
from pycil.dependencies import process_resources
from pycil.vocabulary.generation import claim, execute, recover


@asynccontextmanager
async def ownership(engine):
    async with engine.connect() as connection:
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended('pycil-generation-worker',0))")
        )
        pid = await connection.scalar(text("SELECT pg_backend_pid()"))
        await connection.commit()
        if not acquired:
            raise RuntimeError("worker_already_running")

        async def ensure_owner():
            if connection.invalidated or connection.closed:
                raise RuntimeError("worker_ownership_lost")
            current = await connection.scalar(text("SELECT pg_backend_pid()"))
            await connection.commit()
            if current != pid:
                raise RuntimeError("worker_ownership_lost")

        try:
            yield ensure_owner
        finally:
            if not connection.invalidated and not connection.closed:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended('pycil-generation-worker',0))")
                )
                await connection.commit()


async def run(resources, config, *, once=False):
    async with ownership(resources.engine) as ensure_owner:
        await recover(resources.sessions, config)
        last_purge = 0.0

        async def loop():
            nonlocal last_purge
            while True:
                await ensure_owner()
                row = await claim(resources.sessions, config)
                if row is not None:
                    await execute(resources.sessions, resources.lexicon, row, config, ensure_owner)
                if (
                    asyncio.get_running_loop().time() - last_purge
                    >= config.assistant.purge_interval_seconds
                ):
                    from pycil.assistant.conversations import purge

                    await purge(resources, config)
                    last_purge = asyncio.get_running_loop().time()
                if once:
                    return
                await asyncio.sleep(config.generation.worker.poll_interval_seconds)

        async def monitor():
            while True:
                await asyncio.sleep(config.generation.worker.poll_interval_seconds)
                async with asyncio.timeout(config.generation.worker.poll_interval_seconds + 5):
                    await ensure_owner()

        # Serialize reads on the dedicated coordination connection.
        original = ensure_owner
        mutex = asyncio.Lock()

        async def ensure_owner():
            async with mutex:
                await original()

        work, watch = asyncio.create_task(loop()), asyncio.create_task(monitor())
        try:
            done, _ = await asyncio.wait([work, watch], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            work.cancel()
            watch.cancel()
            await asyncio.gather(work, watch, return_exceptions=True)


async def start(*, check=False, once=False):
    config, deployment = load_config(), Deployment.from_environment()
    async with process_resources(config, deployment) as resources:
        if not check:
            await run(resources, config, once=once)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--once", action="store_true", help="process at most one queued request")
    args = parser.parse_args()
    try:
        asyncio.run(start(check=args.check, once=args.once))
    except KeyboardInterrupt:
        return
    except Exception:
        parser.exit(
            1, "Worker failed; verify config, services, migration gate and exclusive ownership.\n"
        )
    if args.check:
        print("Worker bootstrap verified; no generation or user-unit debit performed.")


if __name__ == "__main__":
    main()
