import asyncio
import os
import socket
import sys

import httpx


def environment(deployment):
    return {
        **os.environ,
        "DB_URL": deployment.db_url.get_secret_value(),
        "REDIS_URL": deployment.redis_url.get_secret_value(),
        "CLERK_JWKS_URL": deployment.clerk_jwks_url,
        "CLERK_ISSUER": deployment.clerk_issuer,
        "CLERK_AUDIENCE": deployment.clerk_audience or "",
        "CLERK_SECRET_KEY": deployment.clerk_secret_key.get_secret_value(),
        "LEXI_CAMBRIDGE_DB_PATH": str(deployment.cambridge_path),
        "INFERENCE_API_KEY": deployment.inference_api_key.get_secret_value(),
        "INFERENCE_BASE_URL": deployment.inference_base_url,
        "LEXI_DECISION_API_KEY": deployment.decision_api_key.get_secret_value(),
        "LEXI_DECISION_BASE_URL": deployment.decision_base_url,
    }


async def command(*args, env):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        *args,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=30)
        assert process.returncode == 0, output.decode()
        return output.decode()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_actual_api_worker_processes_restart_without_schema_repair(deployment):
    env = environment(deployment)
    for _ in range(2):
        output = await command("-m", "pycil.worker", "--check", env=env)
        assert "no generation or user-unit debit" in output
        await command("-m", "pycil.worker", "--once", env=env)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "uvicorn",
            "pycil.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
                async with asyncio.timeout(30):
                    while True:
                        assert process.returncode is None, (await process.communicate())[0].decode()
                        try:
                            response = await client.get("/ready")
                            if response.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(0.1)
                assert (await client.get("/openapi.json")).status_code == 200
                assert (await client.get("/v1/me")).status_code == 401
        finally:
            if process.returncode is None:
                process.terminate()
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=10)
            except TimeoutError:
                process.kill()
                output, _ = await process.communicate()
            assert process.returncode in (0, -15), output.decode()
