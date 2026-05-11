"""Re-export of FakeScript factories for TUI flow tests.

Mirrors :mod:`tests.e2e_chat.helpers.scenarios` exactly so chat and
TUI flows speak the same scripted-LLM vocabulary.
"""

from __future__ import annotations

from tests.e2e_chat.helpers.scenarios import (
    chat_echo,
    cold_start,
    fail,
    multiturn_drain,
    permission_gate,
    slow,
    streaming,
    tool_call,
)

__all__ = [
    "chat_echo",
    "cold_start",
    "fail",
    "multiturn_drain",
    "permission_gate",
    "slow",
    "streaming",
    "tool_call",
]
