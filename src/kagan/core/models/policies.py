from __future__ import annotations

from kagan.core.models.enums import TaskStatus


def transition_status_from_agent_complete(current_status: TaskStatus, success: bool) -> TaskStatus:
    """Return next status after an implementation agent run completes."""
    if success and current_status == TaskStatus.IN_PROGRESS:
        return TaskStatus.REVIEW
    return current_status


def transition_status_from_review_pass(current_status: TaskStatus) -> TaskStatus:
    """Return next status after review approval."""
    if current_status == TaskStatus.REVIEW:
        return TaskStatus.DONE
    return current_status


def transition_status_from_review_reject(current_status: TaskStatus) -> TaskStatus:
    """Return next status after review rejection."""
    if current_status == TaskStatus.REVIEW:
        return TaskStatus.IN_PROGRESS
    return current_status
