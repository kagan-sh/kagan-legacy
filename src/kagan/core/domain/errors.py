"""Domain exception classes for Kagan core."""

from __future__ import annotations

TASK_NOT_FOUND_CODE = "TASK_NOT_FOUND"
_TASK_NOT_FOUND_HINT = "Check task_id with task_list."


def task_not_found_message(task_id: str) -> str:
    """Return the canonical task-not-found message used by command/MCP surfaces."""
    return f"Task {task_id} not found. {_TASK_NOT_FOUND_HINT}"


def task_not_found_response(
    task_id: str,
    *,
    success: bool = False,
    include_task_id: bool = True,
) -> dict[str, object]:
    """Return the canonical structured task-not-found response payload."""
    response: dict[str, object] = {
        "success": success,
        "message": task_not_found_message(task_id),
        "code": TASK_NOT_FOUND_CODE,
    }
    if include_task_id:
        response["task_id"] = task_id
    return response


class SessionError(ValueError):
    """Base for session-related domain errors with a machine-readable code."""

    def __init__(self, message: str, *, code: str, task_id: str) -> None:
        super().__init__(message)
        self.code = code
        self.task_id = task_id


class TaskNotFoundError(SessionError):
    """Raised when the target task does not exist."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task {task_id} not found", code=TASK_NOT_FOUND_CODE, task_id=task_id)


class TaskTypeMismatchError(SessionError):
    """Raised when a non-PAIR task is used for session ops."""

    def __init__(self, task_id: str, current_task_type: str) -> None:
        super().__init__(
            "Only PAIR tasks support interactive session handoff",
            code="TASK_TYPE_MISMATCH",
            task_id=task_id,
        )
        self.current_task_type = current_task_type


class WorkspaceNotFoundError(SessionError):
    """Raised when no workspace exists for the task."""

    def __init__(self, task_id: str) -> None:
        super().__init__(
            f"No workspace found for task {task_id}",
            code="WORKSPACE_NOT_FOUND",
            task_id=task_id,
        )


class InvalidWorktreePathError(SessionError):
    """Raised when a provided worktree_path is invalid or mismatched."""

    def __init__(self, task_id: str, message: str) -> None:
        super().__init__(message, code="INVALID_WORKTREE_PATH", task_id=task_id)


class SessionCreateFailedError(SessionError):
    """Raised when the underlying session backend fails."""

    def __init__(self, task_id: str, cause: Exception) -> None:
        super().__init__(
            f"Failed to create session: {cause}",
            code="SESSION_CREATE_FAILED",
            task_id=task_id,
        )
        self.__cause__ = cause


class ReviewOperationError(ValueError):
    """Base for structured review errors with machine-readable fields."""

    def __init__(self, *, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_payload(self) -> dict[str, str]:
        payload = {"code": self.code, "message": self.message}
        if self.hint is not None and self.hint.strip():
            payload["hint"] = self.hint
        return payload


class ReviewGuardrailBlockedError(ReviewOperationError):
    """Structured REVIEW guardrail failure with machine-readable fields."""


class ReviewApprovalContextMissingError(ReviewOperationError):
    """Raised when approval cannot be persisted due to missing review execution context."""
