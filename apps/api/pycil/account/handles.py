"""Generate public handles without a read-before-write uniqueness check."""

import re
import unicodedata
from uuid import uuid4


def generate_handle(display_name: str) -> str:
    name = unicodedata.normalize("NFKD", display_name.lower().replace("đ", "d"))
    name = "".join(char for char in name if not unicodedata.combining(char))
    stem = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    if not stem or not stem[0].isalpha():
        stem = "user_" + stem
    return stem[:21].rstrip("_") + "_" + uuid4().hex[:8]
