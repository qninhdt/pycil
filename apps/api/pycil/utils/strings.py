"""Unicode normalization, accent stripping, slugification, and string analysis."""

import re
import unicodedata


def strip_accents(text: str) -> str:
    """Normalize Unicode diacritics and convert special characters (e.g. Vietnamese đ/Đ)."""
    normalized = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def slugify(text: str, delimiter: str = "_") -> str:
    """Convert arbitrary text into a clean alphanumeric slug using the specified delimiter."""
    name = strip_accents(text.lower())
    return re.sub(r"[^a-z0-9]+", delimiter, name).strip(delimiter)


def normalize_nfkc_whitespace(text: str) -> str:
    """Normalize string using Unicode NFKC and collapse internal whitespace."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def has_control_or_invisible_chars(text: str) -> bool:
    """Check if the string contains control characters (< 32) or format characters (Unicode Cf)."""
    return any(ord(char) < 32 or unicodedata.category(char) == "Cf" for char in text)


def ngrams(value: str, n: int = 3) -> set[str]:
    """Generate a set of n-character substrings (n-grams) from a string."""
    if n <= 0:
        raise ValueError("n must be a positive integer")
    if len(value) < n:
        return set()
    return {value[position : position + n] for position in range(len(value) - n + 1)}


def phrase_to_flexible_regex(phrase: str) -> str:
    """Convert a literal phrase into a regex pattern allowing flexible whitespace."""
    return re.escape(phrase).replace(r"\ ", r"\s+")
