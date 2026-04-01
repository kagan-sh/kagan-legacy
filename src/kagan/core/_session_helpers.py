"""Session utility functions — process management and classification."""

import os
import signal
import sys
from typing import Any, TypedDict

from kagan.core.errors import (
    AgentRateLimitError,
    AgentRepetitionError,
    AgentTimeoutError,
)
from kagan.core.models import Task


class DetachResult(TypedDict):
    task_id: str
    status: str
    ready_for_review: bool
    pending_changes: bool
    base_branch: str


def terminate_process(pid: int) -> None:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_TERMINATE = 0x0001
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            kernel32.TerminateProcess(handle, 1)
            kernel32.CloseHandle(handle)
    else:
        os.kill(pid, signal.SIGTERM)


def process_exists(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False


def is_shutdown_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc)
    return "Executor shutdown has been called" in message or "Event loop is closed" in message


def agent_timeout_seconds(raw: Any) -> int:
    """Parse the detached-agent timeout setting with a safe default."""
    if raw in (None, ""):
        return 3600
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return 3600


def classify_agent_error(exc: BaseException) -> str:
    """Return a classification string for AGENT_FAILED payloads."""
    if isinstance(exc, AgentRepetitionError):
        return "repetition"
    if isinstance(exc, AgentTimeoutError):
        return "timeout"
    if isinstance(exc, AgentRateLimitError):
        return "rate_limit"
    msg = str(exc).lower()
    if "rate limit" in msg or "rate_limit" in msg or "429" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    return "unknown"


def build_attached_startup_prompt(task: Task) -> str:
    description = (task.description or "").strip()
    criteria = [item.strip() for item in task.acceptance_criteria if item and item.strip()]

    lines = [
        f"# Interactive Task: {task.id} — {task.title}",
        "",
        "Act as a Senior Developer collaborating on this implementation.",
        "",
        "## Task Overview",
        f"**Title:** {task.title}",
        "",
    ]
    if description:
        lines.extend([f"**Description:** {description}", ""])
    if criteria:
        lines.append("## Acceptance Criteria")
        lines.extend(f"- {item}" for item in criteria)
        lines.append("")
    lines.extend(
        [
            "## Important Rules",
            "- You are in a git worktree, NOT the main repository",
            "- Only modify files within this worktree",
            "- COMMIT all changes before finishing (semantic commits: feat:, fix:, docs:, etc.)",
            "- When complete: commit your work, then call `run_detach`",
            "- Your tools are available via the connected MCP server (WORKER role)",
            "",
            "## Coordination Workflow",
            "",
            "Before implementing:",
            "1. Call `task_list` to check for parallel IN_PROGRESS tasks",
            "2. Review concurrent tasks to avoid overlapping file modifications",
            "3. Call `task_events` on related completed tasks to learn from prior work",
            "",
            "## Completion",
            "",
            "1. Implement and verify against acceptance criteria",
            "2. Commit with clear WHY-focused message",
            "3. Call `run_detach` to signal completion",
        ]
    )
    return "\n".join(lines).strip() + "\n"


__all__ = [
    "DetachResult",
    "agent_timeout_seconds",
    "build_attached_startup_prompt",
    "classify_agent_error",
    "is_shutdown_runtime_error",
    "process_exists",
    "terminate_process",
]
