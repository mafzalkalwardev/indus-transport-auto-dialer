"""Rotating file log for dialer operations (watchdog, retries, errors)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from src.paths import LOGS_DIR

_LOG_PATH = None
_LOGGER = None


def setup_dialer_logging() -> logging.Logger:
    global _LOG_PATH, _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    import os
    os.makedirs(LOGS_DIR, exist_ok=True)
    _LOG_PATH = os.path.join(LOGS_DIR, "dialer.log")

    logger = logging.getLogger("indus_dialer")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = RotatingFileHandler(
            _LOG_PATH, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)
    _LOGGER = logger
    return logger


def log_info(msg: str) -> None:
    setup_dialer_logging().info(msg)


def log_warning(msg: str) -> None:
    setup_dialer_logging().warning(msg)


def log_error(msg: str) -> None:
    setup_dialer_logging().error(msg)


def log_path() -> str:
    setup_dialer_logging()
    return _LOG_PATH or ""


def log_call_event(event: dict) -> None:
    """Emit one structured JSON line per call outcome for log parsers."""
    import json

    setup_dialer_logging().info(
        "CALL_EVENT " + json.dumps(event, separators=(",", ":"), default=str)
    )
