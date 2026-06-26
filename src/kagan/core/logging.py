"""Logging configuration for kagan - single Loguru file sink, XDG-compliant paths."""

import atexit
import os
import re
import sys
import threading
from pathlib import Path

from loguru import logger

# Redact common credential shapes before anything reaches the log sink.
_SECRET_RE = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[A-Z0-9]{16}|"
    r"(?:api[_-]?key|secret|token|password)\s*[:=]\s*\S+)"
)


def _scrub_secrets(text: str) -> str:
    return _SECRET_RE.sub("«redacted»", text)


_lock = threading.Lock()
_configured = False
_verbose_added = False
_atexit_registered = False

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}"


def _scrub_log_record(record: dict) -> bool:
    message = record["message"]
    if isinstance(message, str):
        record["message"] = _scrub_secrets(message)
    return True


def default_log_path() -> Path:
    from platformdirs import user_log_dir

    return Path(user_log_dir("kagan", "kagan")) / "kagan.log"


def configure_logging(*, log_level: str = "INFO", verbose: bool = False) -> None:
    global _configured, _verbose_added, _atexit_registered

    with _lock:
        level = os.environ.get("KAGAN_LOG_LEVEL", log_level).upper()

        if not _configured:
            _configured = True
            logger.remove()

            log_path = default_log_path()
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                logger.add(  # type: ignore[no-matching-overload]  # loguru stub: filter callable record type unexposed
                    log_path,
                    level=level,
                    format=LOG_FORMAT,
                    rotation="10 MB",
                    retention=3,
                    enqueue=True,
                    diagnose=False,
                    backtrace=True,
                    filter=_scrub_log_record,
                )
                if not _atexit_registered:
                    _atexit_registered = True
                    atexit.register(logger.complete)
            except OSError as exc:
                logger.add(sys.stderr, level="WARNING")
                logger.error("Failed to setup file logging: {}", exc)

        if verbose and not _verbose_added:
            _verbose_added = True
            logger.add(sys.stderr, level=level, format=LOG_FORMAT, filter=_scrub_log_record)  # type: ignore[no-matching-overload]  # loguru stub: filter callable record type unexposed
