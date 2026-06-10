"""Builtin question plugins.

Importing this package self-registers every builtin question type into
:mod:`shared.questions.registry`. Adding a new builtin type = add a module here
and import it below. Drop-in (third-party) plugins import + register from their
own package instead.
"""
from __future__ import annotations

from shared.questions.plugins import fill_in_blank  # noqa: F401
from shared.questions.plugins import multiple_choice  # noqa: F401
from shared.questions.plugins import write  # noqa: F401

__all__ = ["multiple_choice", "write", "fill_in_blank"]
