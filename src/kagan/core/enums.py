"""Core enums for kagan.core — v2 task lifecycle.

The Inbox urgency order and gate/drift conditions (TUI-INBOX-01) are added during
the rebuild; this holds only the lifecycle states a task moves through
(TUI-SHELL-03).
"""

from enum import StrEnum


class TaskState(StrEnum):
    # Listed in lifecycle order: local work, then the local review gate, then
    # ship, then the remote PR (pr_open), then merged.
    INTAKE = "intake"
    RUNNING = "running"
    VALIDATING = "validating"
    REVIEW = "review"  # local review gate (pre-ship) -> Gate surface
    READY = "ready"
    PR_OPEN = "pr_open"  # PR open on the remote, CI watching (post-ship) -> Workspaces
    DONE = "done"


def humanize_task_state(state: TaskState) -> str:
    """Return the title-cased display label for a task state (e.g. ``Validating``)."""
    return state.value.replace("_", " ").title()


__all__ = ["TaskState", "humanize_task_state"]
