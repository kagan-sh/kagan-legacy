"""Shared type aliases for kagan.tui."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from kagan.core.enums import Priority, TaskStatus

__all__ = [
    "ChatTargetKind",
    "MessageHandler",
    "ModalActionResult",
    "ProjectView",
    "RepoView",
    "ScreenResult",
    "TaskData",
    "TaskUpdateResult",
    "TaskView",
]


class ProjectView(Protocol):
    id: str
    name: str


class RepoView(Protocol):
    id: str
    project_id: str | None
    name: str
    path: str
    default_branch: str


class TaskData(Protocol):
    id: str
    title: str
    description: str
    status: TaskStatus
    priority: Priority


class TaskView(Protocol):
    id: str
    project_id: str
    title: str
    description: str
    status: TaskStatus
    priority: Priority
    agent_backend: str | None
    base_branch: str | None
    acceptance_criteria: list[str]


class TaskUpdateResult(Protocol):
    title: str
    description: str
    priority: Priority
    task_type: str | None
    agent_backend: str | None
    terminal_backend: str | None
    acceptance_criteria: list[str]
    base_branch: str | None
    status: TaskStatus | None


class ModalActionResult(Protocol):
    action: str


ScreenResult = TaskUpdateResult | ModalActionResult | dict[str, object] | None


MessageHandler = Callable[..., Awaitable[None] | None]


class ChatTargetKind(Protocol):
    key: str
    kind: str
    label: str
    task_id: str | None
