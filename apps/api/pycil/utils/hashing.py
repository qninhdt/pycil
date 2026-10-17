"""Standard SHA-256 digests and canonical JSON fingerprinting."""

import hashlib

import orjson


def sha256_hex(data: str | bytes) -> str:
    """Compute the SHA-256 hexadecimal digest of text or bytes."""
    encoded = data.encode() if isinstance(data, str) else data
    return hashlib.sha256(encoded).hexdigest()


def sha256_canonical_json(data: object) -> str:
    """Serialize data using orjson with sorted keys and return its SHA-256 hex digest."""
    encoded = orjson.dumps(data, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(encoded).hexdigest()
