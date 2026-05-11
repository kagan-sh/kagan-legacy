"""Text normalisers — strip volatile bits before snapshot comparison.

Drift sources:
- ULIDs / UUIDs in session and task ids
- ISO-8601 timestamps
- PIDs and TCP ports
- Tmp-dir paths
- ANSI / OSC escape sequences

Each normaliser is idempotent and order-independent.
"""

from __future__ import annotations

import re

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07\x1B]*(?:\x07|\x1B\\))")
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_ULID_RE = re.compile(r"\b[0-9A-HJKMNP-TV-Z]{26}\b")
_ISO_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_PID_RE = re.compile(r"\bpid[=: ]\s*\d+", re.IGNORECASE)
_PORT_RE = re.compile(
    r":\b(?:1[6-9]\d{3}|[2-9]\d{4}|6553[0-5]|655[0-2]\d"
    r"|65[0-4]\d{2}|6[0-4]\d{3}|[1-5]\d{4}|[1-9]\d{3})\b"
)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def mask_uuids(text: str) -> str:
    return _UUID_RE.sub("<uuid>", text)


def mask_ulids(text: str) -> str:
    return _ULID_RE.sub("<ulid>", text)


def mask_timestamps(text: str) -> str:
    return _ISO_TS_RE.sub("<ts>", text)


def mask_pids(text: str) -> str:
    return _PID_RE.sub("pid=<pid>", text)


def mask_ports(text: str) -> str:
    return _PORT_RE.sub(":<port>", text)


def mask_tmp_paths(text: str, tmp_root: str) -> str:
    """Replace ``tmp_root`` prefix occurrences with ``<tmp>``."""
    if not tmp_root:
        return text
    return text.replace(tmp_root, "<tmp>")


def normalise(text: str, *, tmp_root: str = "") -> str:
    """Apply the standard normalisation chain."""
    out = strip_ansi(text)
    out = mask_uuids(out)
    out = mask_ulids(out)
    out = mask_timestamps(out)
    out = mask_pids(out)
    out = mask_ports(out)
    if tmp_root:
        out = mask_tmp_paths(out, tmp_root)
    return out
