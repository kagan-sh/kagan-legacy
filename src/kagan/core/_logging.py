"""Logging configuration for kagan - single Loguru file sink, XDG-compliant."""

import os
import sys
import threading
from pathlib import Path

from loguru import logger

_lock = threading.Lock()
_configured = False
_verbose_added = False

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}"


def default_log_path() -> Path:
    """Return log file path using platformdirs."""
    from platformdirs import user_log_dir

    return Path(user_log_dir("kagan", "kagan")) / "kagan.log"


def configure_logging(*, log_level: str = "INFO", verbose: bool = False) -> None:
    """Loguru configuration. Safe to call multiple times (idempotent).

    The file sink is set up once. A stderr sink is added only when *verbose* is
    True and has not been added yet, so the CLI can upgrade logging after the
    initial import-time call in ``kagan.core.__init__``.

    Args:
        log_level: Level for file sink. Reads KAGAN_LOG_LEVEL env var as override.
        verbose: If True, also add a stderr sink for console output.
    """
    global _configured, _verbose_added

    with _lock:
        level = os.environ.get("KAGAN_LOG_LEVEL", log_level).upper()

        if not _configured:
            _configured = True
            logger.remove()

            log_path = default_log_path()
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                logger.add(
                    log_path,
                    level=level,
                    format=LOG_FORMAT,
                    rotation="10 MB",
                    retention=3,
                    enqueue=True,
                )
            except OSError as exc:
                # Fall back to stderr-only logging
                logger.add(sys.stderr, level="WARNING")
                logger.error("Failed to setup file logging: {}", exc)

        if verbose and not _verbose_added:
            _verbose_added = True
            logger.add(sys.stderr, level=level, format=LOG_FORMAT)
