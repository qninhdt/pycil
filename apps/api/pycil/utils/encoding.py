"""Base64url unpadded encoding and decoding (RFC 4648 §5)."""

import base64


def base64url_encode(data: bytes) -> str:
    """Encode bytes to an unpadded URL-safe base64 string."""
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def base64url_decode(token: str) -> bytes:
    """Decode an unpadded (or padded) URL-safe base64 string."""
    padding = "=" * (-len(token) % 4)
    return base64.b64decode(token + padding, altchars=b"-_", validate=True)
