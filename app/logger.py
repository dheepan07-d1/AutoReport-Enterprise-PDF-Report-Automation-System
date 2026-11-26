"""Centralized logging configuration for AutoReport."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.exceptions import ConfigurationError

DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def close_logger_handlers(logger: logging.Logger) -> None:
    """Close and remove all handlers attached to a logger."""
    for handler in list(logger.handlers):
        try:
            handler.flush()
            handler.close()
        finally:
            logger.removeHandler(handler)


def setup_logger(
    name: str = "autoreport",
    log_file: Path | None = None,
    log_level: str = "INFO",
    console: bool = False,
) -> logging.Logger:
    """Configure and return a rotating file logger for AutoReport.

    Args:
        name: Logger name.
        log_file: Path to the log file. If omitted, logs to ``logs/app.log`` under cwd.
        log_level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        console: Whether to also attach a StreamHandler for stderr/stdout logging.

    Returns:
        Configured ``logging.Logger`` instance.

    Raises:
        ConfigurationError: If the log level is invalid or log file cannot be created.
    """
    normalized_level = log_level.strip().upper()
    if normalized_level not in VALID_LOG_LEVELS:
        raise ConfigurationError(
            f"Invalid log level '{log_level}'. Must be one of {sorted(VALID_LOG_LEVELS)}."
        )

    target_log_file = log_file if log_file is not None else Path("logs") / "app.log"
    try:
        target_log_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(
            f"Unable to create log directory '{target_log_file.parent}': {exc}"
        ) from exc

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, normalized_level))
    logger.propagate = False

    # Reset handlers so repeated initialization or test runs use the exact requested target.
    close_logger_handlers(logger)

    formatter = logging.Formatter(fmt=DEFAULT_LOG_FORMAT, datefmt=DEFAULT_DATE_FORMAT)

    try:
        file_handler = RotatingFileHandler(
            filename=target_log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError as exc:
        raise ConfigurationError(
            f"Unable to open log file '{target_log_file}': {exc}"
        ) from exc

    file_handler.setLevel(getattr(logging, normalized_level))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(getattr(logging, normalized_level))
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger
