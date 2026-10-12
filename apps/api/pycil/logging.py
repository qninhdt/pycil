"""Unified structured logging configuration combining structlog and standard library logging."""

import logging
import os
import sys
from typing import Any

import structlog


def configure_logging(
    log_format: str | None = None,
    log_level: str | int | None = None,
) -> None:
    """Configures structlog and standard library logging for unified output."""
    if log_format is None:
        env_format = os.getenv("LOG_FORMAT", "").strip().lower()
        if env_format in {"json", "console"}:
            log_format = env_format
        else:
            log_format = "console" if sys.stdout.isatty() else "json"

    level_map = logging.getLevelNamesMapping()
    if log_level is None:
        env_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        resolved_level = level_map.get(env_level, logging.INFO)
    elif isinstance(log_level, str):
        resolved_level = level_map.get(log_level.strip().upper(), logging.INFO)
    else:
        resolved_level = int(log_level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.ExtraAdder(),
            *shared_processors,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(resolved_level)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(resolved_level)

    # Route uvicorn loggers to root handler and delegate level filtering to root
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi"):
        sub_logger = logging.getLogger(logger_name)
        sub_logger.handlers.clear()
        sub_logger.propagate = True
        sub_logger.setLevel(logging.NOTSET)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Returns a bound structlog logger."""
    return structlog.get_logger(name)


def bind_contextvars(**kwargs: Any) -> None:
    """Binds key-values into async-local contextvars for all subsequent log events."""
    structlog.contextvars.bind_contextvars(**kwargs)


def bound_contextvars(**kwargs: Any):
    """Context manager binding key-values into contextvars, unbinding on exit."""
    return structlog.contextvars.bound_contextvars(**kwargs)


def clear_contextvars() -> None:
    """Clears all bound contextvars for the current task/request."""
    structlog.contextvars.clear_contextvars()


def unbind_contextvars(*keys: str) -> None:
    """Unbinds specified keys from contextvars."""
    structlog.contextvars.unbind_contextvars(*keys)
