"""Repetition guard — detects agents stuck in tool-call loops."""

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any


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


@dataclass(slots=True)
class RepetitionGuard:
    """Tracks recent tool calls to detect repetitive patterns.

    If the same tool call (same name + argument hash) appears >= threshold times
    within the sliding window, the guard returns True, signaling a loop condition.
    """

    window: int = 20
    """Size of the sliding window for tracking calls."""

    threshold: int = 8
    """Number of repetitions before signaling a loop."""

    _recent: deque[str] = field(default_factory=deque)
    """FIFO deque of recent tool call keys."""

    def check(self, tool_name: str, arguments: Any) -> bool:
        """Check if a tool call is repetitive.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments (dict, JSON string, None, or any type)

        Returns:
            True if the call appears repetitive (same call >= threshold times in window)
        """
        arg_hash = hashlib.blake2s(
            _normalize_for_hash(arguments).encode(), digest_size=8
        ).hexdigest()
        key = f"{tool_name}:{arg_hash}"

        self._recent.append(key)
        if len(self._recent) > self.window:
            self._recent.popleft()

        count = sum(1 for k in self._recent if k == key)
        return count >= self.threshold

    def reset(self) -> None:
        """Clear the recent calls history."""
        self._recent.clear()
