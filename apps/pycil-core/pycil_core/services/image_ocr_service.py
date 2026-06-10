"""Image-OCR ingestion.

Receives an uploaded image, runs `tesseract` (or stub when env unset),
extracts candidate words, dedupes against deck, and pipes through
term_batch_service.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile

_log = logging.getLogger(__name__)


_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]{2,}\b")


def extract_terms(image_bytes: bytes, *, max_terms: int = 50) -> list[str]:
    """Returns OCR'd candidate terms.

    No-op when tesseract isn't installed — caller falls back to "manual paste".
    """
    if not _has_tesseract():
        _log.info("ocr_skipped_tesseract_missing")
        return []
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as f:
        f.write(image_bytes)
        f.flush()
        try:
            result = subprocess.run(  # noqa: S603 — tesseract path resolved by which()
                ["tesseract", f.name, "-", "-l", "eng"],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            _log.warning("ocr_failed", extra={"err": str(exc)[:200]})
            return []
    text_out = result.stdout
    seen: set[str] = set()
    out: list[str] = []
    for m in _WORD_RE.finditer(text_out):
        word = m.group(0).lower()
        if word in seen:
            continue
        seen.add(word)
        out.append(word)
        if len(out) >= max_terms:
            break
    return out


def _has_tesseract() -> bool:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(path, "tesseract")
        if os.access(candidate, os.X_OK):
            return True
    return False
