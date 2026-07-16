"""Opt-in broker proof for the native Centrifugo v5 user-limited ACL."""

import asyncio
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import jwt
import pytest
import websockets

pytestmark = pytest.mark.live_centrifugo

_SECRET = "0123456789abcdef0123456789abcdef"


@pytest.mark.skipif(
    os.environ.get("RUN_CENTRIFUGO_LIVE") != "1",
    reason="set RUN_CENTRIFUGO_LIVE=1 to run the Docker-backed broker check",
)
def test_centrifugo_rejects_cross_user_subscription():
    """A valid A connection must not subscribe to B's ``#B`` channel."""
    name = f"pycil-acl-{uuid.uuid4().hex}"
    root = Path(__file__).parents[4]
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-p",
            "18001:8000",
            "-e",
            f"CENTRIFUGO_TOKEN_HMAC_SECRET_KEY={_SECRET}",
            "-e",
            "CENTRIFUGO_API_KEY=test-api-key",
            "-v",
            f"{root / 'centrifugo-config.json'}:/centrifugo/config.json:ro",
            "centrifugo/centrifugo:v5",
            "centrifugo",
            "-c",
            "/centrifugo/config.json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        # Docker reports the container started before its WebSocket listener is
        # accepting connections; keep this intentional live check deterministic.
        time.sleep(1)
        asyncio.run(_assert_acl())
    finally:
        subprocess.run(["docker", "stop", name], check=False, capture_output=True)


async def _assert_acl() -> None:
    user_a, user_b = "user-a", "user-b"
    now = int(time.time())
    token = jwt.encode({"sub": user_a, "exp": now + 60}, _SECRET, algorithm="HS256")
    async with websockets.connect("ws://127.0.0.1:18001/connection/websocket") as ws:
        await ws.send(json.dumps({"id": 1, "connect": {"token": token}}))
        assert "connect" in json.loads(await ws.recv())
        await ws.send(
            json.dumps(
                {"id": 2, "subscribe": {"channel": f"users:{user_a}:jobs:1#{user_a}"}}
            )
        )
        assert "subscribe" in json.loads(await ws.recv())
        await ws.send(
            json.dumps(
                {"id": 3, "subscribe": {"channel": f"users:{user_b}:jobs:1#{user_b}"}}
            )
        )
        reply = json.loads(await ws.recv())
        assert reply["error"]["code"] == 103
