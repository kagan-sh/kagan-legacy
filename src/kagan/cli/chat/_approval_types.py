"""Shared types used by both ``_permission_ui`` and ``_approval_batch``.

Breaking the circular import: both modules import from here instead of from
each other.

The pure helpers (``_tool_action_key``, ``_SessionApprovals``,
``_session_approvals``) are re-exported from :mod:`kagan.core.permission_ui`
so the TUI can consume them without crossing the CLI package boundary.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from rich.measure import Measurement
from rich.text import Text

from kagan.cli.chat._renderer import _modal_active as _modal_active  # re-export
from kagan.cli.chat.repl import WAVE_FRAMES
from kagan.core.permission_ui import SessionApprovals as _SessionApprovals
from kagan.core.permission_ui import session_approvals as _session_approvals
from kagan.core.permission_ui import tool_action_key as _tool_action_key

# ---------------------------------------------------------------------------
# Shared dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _DecisionTuple:
    """``(outcome, feedback)`` shape — mirrors ``PermissionDecision``."""

    outcome: str  # one of: allow_once, allow_always, deny, deny_feedback
    feedback: str | None = None


@dataclass(frozen=True, slots=True)
class _SendResult:
    was_cancelled: bool = False


@dataclass(frozen=True, slots=True)
class _WaveIndicator:
    _start: float = field(default_factory=time.monotonic)

    def __rich_console__(self, console, options):
        elapsed = time.monotonic() - self._start
        idx = int(elapsed / 0.10) % len(WAVE_FRAMES)
        yield from console.render(Text(WAVE_FRAMES[idx], style="dim cyan"), options)

    def __rich_measure__(self, console, options):
        del console, options
        return Measurement(len(WAVE_FRAMES[0]), len(WAVE_FRAMES[0]))


def get_session_approvals() -> _SessionApprovals:
    """Return the module-level session approval tracker."""
    return _session_approvals


__all__ = [
    "_DecisionTuple",
    "_SendResult",
    "_SessionApprovals",
    "_WaveIndicator",
    "_modal_active",
    "_session_approvals",
    "_tool_action_key",
    "get_session_approvals",
]
