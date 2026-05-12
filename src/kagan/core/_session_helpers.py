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


def build_attached_startup_prompt(task: Task, criteria_texts: list[str] | None = None) -> str:
    description = (task.description or "").strip()
    # criteria_texts is loaded separately from AcceptanceCriterion table
    criteria = [item.strip() for item in (criteria_texts or []) if item and item.strip()]

    lines = [
        f"# Interactive Task {task.id} — {task.title}",
        "",
        "You are a senior dev co-piloting this work. WORKER role on the kagan MCP.",
        "You are in a git worktree, not the main repo — only modify files here.",
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
            "## Workflow",
            "1. `task_list` for parallel IN_PROGRESS tasks; avoid file overlap.",
            "   `task_events` on related completed tasks for prior learnings.",
            "2. Implement and verify against acceptance criteria.",
            "3. Commit (semantic: feat:/fix:/docs:/...) with a WHY-focused message.",
            "4. `run_detach` to signal completion.",
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
