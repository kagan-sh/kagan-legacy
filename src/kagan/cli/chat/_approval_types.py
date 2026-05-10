"""Shared types used by both ``_permission_ui`` and ``_approval_batch``.

Breaking the circular import: both modules import from here instead of from
each other.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from rich.measure import Measurement
from rich.text import Text

from kagan.cli.chat._renderer import _modal_active as _modal_active  # re-export
from kagan.cli.chat.repl import WAVE_FRAMES

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


# ---------------------------------------------------------------------------
# Tool action key
# ---------------------------------------------------------------------------


def _tool_action_key(tool_call: Any) -> str:
    """Return the base tool name for session-allow tracking (no args embedded).

    Accepts both ACP tool-call objects (with ``title`` / ``name`` attrs) and
    plain dicts (used by the engine's :class:`PermissionRequest` event).
    Strips any trailing ': {...}' argument suffix from the title field so that
    repeated calls to the same tool with different arguments share one key.
    """
    if isinstance(tool_call, dict):
        raw = tool_call.get("title") or tool_call.get("name") or "tool"
    else:
        raw = getattr(tool_call, "title", None) or getattr(tool_call, "name", None) or "tool"
    base = str(raw).split(":")[0].split("{")[0].strip().casefold()
    return base or "tool"


# ---------------------------------------------------------------------------
# Session-allow cache (module-level singleton)
# ---------------------------------------------------------------------------


class _SessionApprovals:
    """Track tool actions approved for the lifetime of this REPL session."""

    def __init__(self) -> None:
        self._allowed: set[str] = set()
        self._all_allowed: bool = False

    def is_allowed(self, action_key: str) -> bool:
        return self._all_allowed or action_key in self._allowed

    def grant(self, action_key: str) -> None:
        self._allowed.add(action_key)

    def grant_all(self) -> None:
        """Trust all tool calls for the rest of this session."""
        self._all_allowed = True

    def revoke(self, action_key: str) -> None:
        self._allowed.discard(action_key)

    def list_granted(self) -> list[str]:
        return sorted(self._allowed)


_session_approvals = _SessionApprovals()


def get_session_approvals() -> _SessionApprovals:
    """Return the module-level session approval tracker."""
    return _session_approvals
