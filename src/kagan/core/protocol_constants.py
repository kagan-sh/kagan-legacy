"""Protocol-facing defaults shared across core commands, SDK, MCP, and clients."""

from __future__ import annotations

# Shared task wait window used by core command handlers and MCP bridge polling.
TASK_WAIT_WINDOW_SECONDS: float = 45.0
TASK_WAIT_IPC_TIMEOUT_BUFFER_SECONDS: float = 5.0
DEFAULT_JOB_WAIT_TIMEOUT_SECONDS: float = 30.0
DEFAULT_IPC_TIMEOUT_SECONDS: float = 30.0

# Shared event pagination defaults used by core/SDK/MCP surfaces.
DEFAULT_EVENTS_LIMIT: int = 50
MAX_EVENTS_LIMIT: int = 100

# Shared task content/pagination defaults used by core handlers and SDK clients.
DEFAULT_TASK_SCRATCHPAD_CHAR_LIMIT: int = 16_000
DEFAULT_TASK_LOG_ENTRY_CHAR_LIMIT: int = 6_000
DEFAULT_TASK_LOG_TOTAL_CHAR_LIMIT: int = 18_000
DEFAULT_TASK_LOG_LIMIT: int = 5
MAX_TASK_LOG_LIMIT: int = 20

__all__ = [
    "DEFAULT_EVENTS_LIMIT",
    "DEFAULT_IPC_TIMEOUT_SECONDS",
    "DEFAULT_JOB_WAIT_TIMEOUT_SECONDS",
    "DEFAULT_TASK_LOG_ENTRY_CHAR_LIMIT",
    "DEFAULT_TASK_LOG_LIMIT",
    "DEFAULT_TASK_LOG_TOTAL_CHAR_LIMIT",
    "DEFAULT_TASK_SCRATCHPAD_CHAR_LIMIT",
    "MAX_EVENTS_LIMIT",
    "MAX_TASK_LOG_LIMIT",
    "TASK_WAIT_IPC_TIMEOUT_BUFFER_SECONDS",
    "TASK_WAIT_WINDOW_SECONDS",
]
