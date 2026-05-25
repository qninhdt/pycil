"""B2 / S3-compatible signed-URL signer for avatar uploads.

`generate_put_url` returns a presigned PUT URL bound to a server-generated
key (`users/{uid}/avatars/{uuid4}.{ext}`) — uuid4 is generated server-side
and never accepted from the client, preventing key-substitution attacks
on signed URLs.
"""
from __future__ import annotations

import functools
from uuid import UUID, uuid4

import boto3
from botocore.config import Config

from pycil_core.config import get_settings


_ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


@functools.lru_cache(maxsize=1)
def _client():
    """Per-process cached boto3 client. Lazy so each forked uvicorn worker
    gets its own client (boto3 clients are not fork-safe)."""
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=getattr(s, "b2_endpoint", None),
        aws_access_key_id=getattr(s, "b2_key_id", None),
        aws_secret_access_key=getattr(s, "b2_application_key", None),
        config=Config(signature_version="s3v4"),
    )


async def generate_put_url(
    *, user_id: UUID, content_type: str, expires_in: int = 900
) -> dict[str, object]:
    if content_type not in _ALLOWED_TYPES:
        raise ValueError("unsupported_content_type")
    s = get_settings()
    bucket = getattr(s, "b2_bucket", None)
    if not bucket:
        raise RuntimeError("b2_bucket_not_configured")
    ext = _ALLOWED_TYPES[content_type]
    key = f"users/{user_id}/avatars/{uuid4().hex}.{ext}"
    import asyncio
    url = await asyncio.to_thread(
        _client().generate_presigned_url,
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )
    public_prefix = getattr(s, "b2_public_url_prefix", "").rstrip("/")
    return {
        "put_url": url,
        "key": key,
        "public_url": f"{public_prefix}/{key}" if public_prefix else None,
        "expires_in": expires_in,
    }
