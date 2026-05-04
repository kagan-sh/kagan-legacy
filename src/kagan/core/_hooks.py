"""Agent lifecycle guard functions — repetition and dangerous-command detection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections import deque


def _normalize_for_hash(arguments: Any) -> str:
    """Normalize tool arguments to a stable string for hashing.

    Handles dict, JSON-encoded string, None, and arbitrary types.
    """
    if arguments is None:
        return ""
    if isinstance(arguments, dict):
        return repr(sorted(arguments.items()))
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return repr(sorted(parsed.items()))
            return repr(parsed)
        except (json.JSONDecodeError, ValueError):
            return arguments
    return repr(arguments)


class HookAction(StrEnum):
    """What a guard function wants the caller to do."""

    CONTINUE = "continue"
    CANCEL_SESSION = "cancel_session"


@dataclass(slots=True)
class HookResult:
    """Return value from a guard function."""

    action: HookAction = HookAction.CONTINUE
    message: str | None = None


_BLOCKED_PATTERNS: tuple[str, ...] = (
    "rm -rf /",
    "git push --force ",  # trailing space avoids matching --force-with-lease
    "git push -f ",
    "git reset --hard",
    "DROP TABLE",
    "DROP DATABASE",
)


def detect_repetition(
    recent: deque[str],
    tool_name: str | None,
    tool_arguments: Any,
    *,
    threshold: int = 8,
) -> HookResult:
    """Detect agents stuck in tool-call loops.

    Appends the current call fingerprint to *recent* (caller owns the deque)
    and returns CANCEL_SESSION if the same fingerprint appears *threshold* or
    more times within the window.
    """
    if tool_name is None:
        return HookResult()

    arg_hash = hashlib.blake2s(
        _normalize_for_hash(tool_arguments).encode(), digest_size=8
    ).hexdigest()
    key = f"{tool_name}:{arg_hash}"

    recent.append(key)

    count = sum(1 for k in recent if k == key)
    if count >= threshold:
        return HookResult(
            action=HookAction.CANCEL_SESSION,
            message="Agent detected in tool-call loop; session cancelled",
        )
    return HookResult()


def detect_dangerous_command(
    tool_name: str | None,
    tool_arguments: Any,
    task_id: str,
) -> HookResult:
    """Block known destructive shell commands.

    Returns CANCEL_SESSION if any blocked pattern is found in *tool_arguments*.
    """
    if tool_name is None or tool_arguments is None:
        return HookResult()

    args_str = str(tool_arguments).lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern.lower() in args_str:
            logger.warning(
                "Dangerous command blocked: pattern={!r} tool={} task={}",
                pattern,
                tool_name,
                task_id,
            )
            return HookResult(
                action=HookAction.CANCEL_SESSION,
                message=f"Blocked dangerous command matching pattern: {pattern!r}",
            )
    return HookResult()
