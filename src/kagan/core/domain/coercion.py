"""Canonical scalar coercion helpers for task and planner payloads."""

from __future__ import annotations

from typing import Literal, cast

from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType

PlanPriorityValue = Literal["low", "medium", "high"]
PlanTodoStatusValue = Literal["pending", "in_progress", "completed", "failed"]

TASK_STATUS_VALUES: tuple[str, ...] = tuple(status.value for status in TaskStatus)
TASK_TYPE_VALUES: tuple[str, ...] = tuple(task_type.value for task_type in TaskType)
_TASK_PRIORITY_VALUES: tuple[str, ...] = ("LOW", "MED", "MEDIUM", "HIGH")

TASK_STATUS_INPUT_VALUES: tuple[str, ...] = TASK_STATUS_VALUES + tuple(
    value.lower() for value in TASK_STATUS_VALUES
)
TASK_TYPE_INPUT_VALUES: tuple[str, ...] = TASK_TYPE_VALUES + tuple(
    value.lower() for value in TASK_TYPE_VALUES
)
TASK_PRIORITY_INPUT_VALUES: tuple[str, ...] = _TASK_PRIORITY_VALUES + tuple(
    value.lower() for value in _TASK_PRIORITY_VALUES
)

PLAN_PRIORITY_VALUES: tuple[PlanPriorityValue, ...] = ("low", "medium", "high")
PLAN_TODO_STATUS_VALUES: tuple[PlanTodoStatusValue, ...] = (
    "pending",
    "in_progress",
    "completed",
    "failed",
)

_TASK_PRIORITY_ALIASES: dict[str, TaskPriority] = {
    "LOW": TaskPriority.LOW,
    "MED": TaskPriority.MEDIUM,
    "MEDIUM": TaskPriority.MEDIUM,
    "HIGH": TaskPriority.HIGH,
}
_PLAN_PRIORITY_BY_TASK_PRIORITY: dict[TaskPriority, PlanPriorityValue] = {
    TaskPriority.LOW: "low",
    TaskPriority.MEDIUM: "medium",
    TaskPriority.HIGH: "high",
}
_PLAN_TODO_STATUS_SET = frozenset(PLAN_TODO_STATUS_VALUES)


def normalize_task_status_text(value: str) -> str:
    """Normalize task status string forms to canonical enum token format."""
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    if normalized == "INPROGRESS":
        return "IN_PROGRESS"
    return normalized


def is_task_type_token(value: object) -> bool:
    """Return True when value represents an AUTO/PAIR task_type token."""
    return coerce_task_type(value) is not None


def coerce_task_status(
    value: object,
    *,
    default: TaskStatus | None = None,
) -> TaskStatus | None:
    """Coerce object to TaskStatus; return default on unsupported value."""
    if isinstance(value, TaskStatus):
        return value
    if isinstance(value, str):
        normalized = normalize_task_status_text(value)
        try:
            return TaskStatus(normalized)
        except ValueError:
            return default
    return default


def coerce_task_priority(
    value: object,
    *,
    default: TaskPriority | None = None,
) -> TaskPriority | None:
    """Coerce object to TaskPriority; return default on unsupported value."""
    if isinstance(value, TaskPriority):
        return value
    if isinstance(value, int):
        try:
            return TaskPriority(value)
        except ValueError:
            return default
    if isinstance(value, str):
        cleaned = value.strip().upper()
        if cleaned.isdigit():
            try:
                return TaskPriority(int(cleaned))
            except ValueError:
                return default
        return _TASK_PRIORITY_ALIASES.get(cleaned, default)
    return default


def coerce_task_type(
    value: object,
    *,
    default: TaskType | None = None,
) -> TaskType | None:
    """Coerce object to TaskType; return default on unsupported value."""
    if isinstance(value, TaskType):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        try:
            return TaskType(normalized)
        except ValueError:
            return default
    return default


def coerce_plan_priority(
    value: object,
    *,
    default: PlanPriorityValue = "medium",
) -> PlanPriorityValue:
    """Coerce planner priority payload to canonical low/medium/high."""
    priority = coerce_task_priority(value)
    if priority is None:
        return default
    return _PLAN_PRIORITY_BY_TASK_PRIORITY[priority]


def coerce_plan_todo_status(
    value: object,
    *,
    default: PlanTodoStatusValue = "pending",
) -> PlanTodoStatusValue:
    """Coerce planner todo status payload to canonical token."""
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized == "inprogress":
            normalized = "in_progress"
        if normalized in _PLAN_TODO_STATUS_SET:
            return cast("PlanTodoStatusValue", normalized)
    return default


def normalize_acceptance_criteria(value: object) -> list[str] | None:
    """Normalize acceptance-criteria payloads.

    Returns:
        A cleaned criteria list when value is ``None``, ``str``, or ``list``;
        ``None`` for unsupported input types.
    """
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if not isinstance(value, list):
        return None
    cleaned: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned


__all__ = [
    "PLAN_PRIORITY_VALUES",
    "PLAN_TODO_STATUS_VALUES",
    "TASK_PRIORITY_INPUT_VALUES",
    "TASK_STATUS_INPUT_VALUES",
    "TASK_STATUS_VALUES",
    "TASK_TYPE_INPUT_VALUES",
    "TASK_TYPE_VALUES",
    "PlanPriorityValue",
    "PlanTodoStatusValue",
    "coerce_plan_priority",
    "coerce_plan_todo_status",
    "coerce_task_priority",
    "coerce_task_status",
    "coerce_task_type",
    "is_task_type_token",
    "normalize_acceptance_criteria",
    "normalize_task_status_text",
]
