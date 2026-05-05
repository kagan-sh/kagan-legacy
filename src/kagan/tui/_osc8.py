"""kagan.tui._osc8 — OSC 8 hyperlink support for capable terminals.

OSC 8 is a de-facto terminal standard for inline hyperlinks:

    ESC ] 8 ; ; <url> ST <text> ESC ] 8 ; ; ST

where ST is the string-terminator sequence ``ESC \\``.  Terminals that do
not understand the sequence display the raw text between the two framing
sequences — so the fallback is plain text, not garbage.

The capability probe checks environment variables rather than probing the
terminal at runtime (which would require a round-trip write/read on the tty
and is unsuitable for a TUI process).  This is the same approach used by
``rich``, ``hyperlink``, and most CLI tools.

Override via ``KAGAN_OSC8=1`` (force on) or ``KAGAN_OSC8=0`` (force off).
``NO_COLOR`` disables OSC 8 when ``KAGAN_OSC8`` is not set, following the
spirit of the NO_COLOR spec (users who disable color want literal output).
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

__all__ = ["file_link", "is_osc8_supported", "link"]

# ST is ESC \\ — the two-character string-terminator for OSC sequences.
# OSC 8 specifically uses the BEL-terminated form too, but ST is preferred
# by modern emulators because BEL (0x07) is ambiguous in some contexts.
_ESC = "\x1b"
_ST = "\x1b\\"

# Environment tokens that identify known OSC 8-capable terminal emulators.
# Apple_Terminal on Big Sur+ supports OSC 8; trust it without probing.
# vscode here is the VS Code integrated terminal (TERM_PROGRAM=vscode).
_TERM_PROGRAM_ALLOWLIST = frozenset({"iTerm.app", "WezTerm", "vscode", "ghostty", "Apple_Terminal"})

# TERM values emitted by emulators that document OSC 8 support.
_TERM_ALLOWLIST = frozenset({"xterm-kitty", "xterm-ghostty", "wezterm", "alacritty"})

# Characters that are illegal inside an OSC 8 URL; they break the sequence
# framing and could be exploited to inject additional escape sequences.
_URL_ILLEGAL = {"\x1b", "\x07", "\n", "\r"}


@functools.cache
def is_osc8_supported() -> bool:
    """Return True if the current terminal is known to support OSC 8.

    The result is cached for the process lifetime; call once and cache.
    """
    override = os.environ.get("KAGAN_OSC8", "").strip()
    if override == "1":
        return True
    if override == "0":
        return False

    # Respect NO_COLOR when no explicit override is set.
    if os.environ.get("NO_COLOR"):
        return False

    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program in _TERM_PROGRAM_ALLOWLIST:
        return True

    term = os.environ.get("TERM", "")
    return term in _TERM_ALLOWLIST


def link(url: str, text: str) -> str:
    """Return an OSC 8 hyperlink string, or plain *text* when unsupported.

    Parameters
    ----------
    url:
        The target URL.  Must not contain ESC, BEL, CR, or LF — these
        characters break the OSC 8 framing and could inject escape sequences.
        Raises ``ValueError`` on invalid input.
    text:
        The visible label for the link.

    Returns
    -------
    str
        ``ESC]8;;<url>ST<text>ESC]8;;ST`` when OSC 8 is supported,
        otherwise plain *text*.
    """
    if not is_osc8_supported():
        return text

    bad = _URL_ILLEGAL.intersection(url)
    if bad:
        escaped = ", ".join(repr(c) for c in sorted(bad))
        raise ValueError(f"URL contains illegal control character(s): {escaped}")

    return f"{_ESC}]8;;{url}{_ST}{text}{_ESC}]8;;{_ST}"


def file_link(path: str, text: str | None = None) -> str:
    """Return an OSC 8 ``file://`` hyperlink for *path*.

    Resolves the path to an absolute URI via :func:`pathlib.Path.as_uri`
    so that spaces and non-ASCII characters in paths are percent-encoded
    correctly.  When OSC 8 is not supported, returns *text* (or *path* if
    *text* is not supplied).

    Parameters
    ----------
    path:
        File-system path (absolute or relative to cwd).
    text:
        Visible label.  Defaults to *path* itself.
    """
    label = text if text is not None else path
    if not is_osc8_supported():
        return label
    try:
        uri = Path(path).resolve().as_uri()
    except (ValueError, OSError):
        # Path.as_uri() raises ValueError for relative Windows paths without a
        # drive letter; fall back to plain label so the UI never breaks.
        return label
    return link(uri, label)
