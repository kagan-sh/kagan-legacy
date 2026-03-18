"""Repetition guard — detects agents stuck in tool-call loops."""

import hashlib
from collections import deque
from dataclasses import dataclass, field


@dataclass(slots=True)
class RepetitionGuard:
    """Tracks recent tool calls to detect repetitive patterns.

    If the same tool call (same name + argument hash) appears >= threshold times
    within the sliding window, the guard returns True, signaling a loop condition.
    """

    window: int = 10
    """Size of the sliding window for tracking calls."""

    threshold: int = 4
    """Number of repetitions before signaling a loop."""

    _recent: deque[str] = field(default_factory=deque)
    """FIFO deque of recent tool call keys."""

    def check(self, tool_name: str, arguments: dict | None) -> bool:
        """Check if a tool call is repetitive.

        Args:
            tool_name: Name of the tool being called
            arguments: Dictionary of arguments (will be hashed)

        Returns:
            True if the call appears repetitive (same call >= threshold times in window)
        """
        # Hash the arguments to avoid storing large payloads
        arg_hash = hashlib.md5(
            repr(sorted(arguments.items()) if arguments else "").encode()
        ).hexdigest()[:8]
        key = f"{tool_name}:{arg_hash}"

        self._recent.append(key)
        if len(self._recent) > self.window:
            self._recent.popleft()

        count = sum(1 for k in self._recent if k == key)
        return count >= self.threshold

    def reset(self) -> None:
        """Clear the recent calls history."""
        self._recent.clear()
