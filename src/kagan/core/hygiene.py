"""Output hygiene helpers for shared/displayed artifacts."""

import re
from pathlib import Path

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ABS_PATH_RE = re.compile(r"(?<![\w:])/(?:[^\s:]+/)*[^\s:]+(?::\d+)?")
_PATH_MARKERS = (".kagan", "src", "tests", "test", "docs", "config")
_NOISY_PREFIXES = (
    "Checking ",
    "Compiling ",
    "Building ",
    "Finished ",
    "Fresh ",
    "Downloaded ",
    "Downloading ",
)
_SIGNAL_RE = re.compile(
    r"error|fail|failed|failure|panic|exception|traceback|diff in |warning",
    re.IGNORECASE,
)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def display_location(location: str | None) -> str:
    """Repo-safe finding label for UI/receipt output."""
    raw = strip_ansi((location or "").strip())
    if not raw or raw == ".":
        return "[repo]"
    return _relativize_absolute_paths(raw)


def distill_check_detail(detail: str) -> str:
    """Strip terminal/local noise and keep the useful failure lines."""
    clean = _relativize_absolute_paths(strip_ansi(detail)).strip()
    if not clean:
        return ""
    lines = [ln.rstrip() for ln in clean.splitlines() if ln.strip()]
    lines = [ln for ln in lines if not ln.lstrip().startswith(_NOISY_PREFIXES)]
    if len(lines) <= 12:
        return "\n".join(lines)
    signal = [ln for ln in lines if _SIGNAL_RE.search(ln)]
    if signal:
        return "\n".join(signal[:12])
    return "\n".join([*lines[:6], "...", *lines[-5:]])


def _relativize_absolute_paths(text: str) -> str:
    return _ABS_PATH_RE.sub(lambda m: _relative_label(m.group(0)), text)


def _relative_label(value: str) -> str:
    suffix = ""
    path_text = value
    match = re.match(r"(.+?)(:\d+)$", value)
    if match:
        path_text, suffix = match.groups()

    path = Path(path_text)
    parts = path.parts
    for marker in _PATH_MARKERS:
        if marker in parts:
            idx = parts.index(marker)
            return "/".join(parts[idx:]) + suffix
    return path.name + suffix


__all__ = ["display_location", "distill_check_detail", "strip_ansi"]
