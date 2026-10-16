"""Generate public handles without a read-before-write uniqueness check."""

from uuid import uuid4

from pycil.utils.strings import slugify


def generate_handle(display_name: str) -> str:
    stem = slugify(display_name)
    if not stem or not stem[0].isalpha():
        stem = "user_" + stem
    return stem[:21].rstrip("_") + "_" + uuid4().hex[:8]
