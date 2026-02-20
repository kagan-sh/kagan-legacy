from __future__ import annotations

# Shared task wait window used by core command handlers and MCP bridge polling.
TASK_WAIT_WINDOW_SECONDS: float = 45.0
TASK_WAIT_IPC_TIMEOUT_BUFFER_SECONDS: float = 5.0

__all__ = ["TASK_WAIT_IPC_TIMEOUT_BUFFER_SECONDS", "TASK_WAIT_WINDOW_SECONDS"]
