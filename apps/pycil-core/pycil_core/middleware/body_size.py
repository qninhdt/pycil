"""Reject oversized request bodies before they reach handlers.

Pure ASGI middleware that buffers the inbound body, counts bytes against the
cap (regardless of `Content-Length` — chunked transfer cannot bypass), and
emits 413 directly when the cap is exceeded. The buffered body is then
replayed to the downstream app.

Multipart uploads bypass pycil-core entirely (B2 PUT via presigned URL), so
a 1 MB default cap is safe for our API surface.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_OVERSIZED_BODY = b'{"detail":"request_body_too_large"}'


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = 1_048_576) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        # Fast-path: trust Content-Length when present and it's already over.
        for hk, hv in scope.get("headers") or []:
            if hk == b"content-length":
                try:
                    if int(hv.decode("latin-1")) > self._max_bytes:
                        await _send_413(send)
                        return
                except (ValueError, UnicodeDecodeError):
                    pass
                break

        # Buffer the body; cap enforced regardless of Content-Length truthfulness.
        chunks: list[bytes] = []
        more_body = True
        seen = 0
        while more_body:
            message = await receive()
            if message.get("type") != "http.request":
                # http.disconnect or anything else: forward to downstream untouched.
                async def replay_disconnect(msg: Message = message) -> Message:
                    return msg

                await self._app(scope, replay_disconnect, send)
                return
            body: bytes = message.get("body") or b""
            seen += len(body)
            if seen > self._max_bytes:
                await _send_413(send)
                return
            chunks.append(body)
            more_body = bool(message.get("more_body"))

        body_iter = iter(chunks)

        async def replay_receive() -> Message:
            try:
                chunk = next(body_iter)
            except StopIteration:
                return {"type": "http.request", "body": b"", "more_body": False}
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": False,
            }

        await self._app(scope, replay_receive, send)


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_OVERSIZED_BODY)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _OVERSIZED_BODY})
