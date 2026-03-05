"""Shared type aliases for kagan.tui."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from kagan.core.enums import Priority, TaskStatus, WorkMode

__all__ = [
    "ChatTargetKind",
    "MessageHandler",
    "ModalActionResult",
    "PluginAction",
    "PluginBadge",
    "PluginForm",
    "PluginUICatalog",
    "ProjectView",
    "RepoView",
    "ScreenResult",
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


class TaskView(Protocol):
    id: str
    project_id: str
    title: str
    description: str
    status: TaskStatus
    priority: Priority
    execution_mode: WorkMode
    agent_backend: str | None
    base_branch: str | None
    acceptance_criteria: list[str]


class TaskUpdateResult(Protocol):
    """Result shape returned from task create/edit modals."""

    title: str
    description: str
    priority: Priority
    execution_mode: WorkMode
    task_type: str | None
    agent_backend: str | None
    terminal_backend: str | None
    acceptance_criteria: list[str]
    base_branch: str | None
    status: TaskStatus | None


class ModalActionResult(Protocol):
    """Result shape for special modal actions (e.g. DELETE)."""

    action: str


# Union of possible screen results.
ScreenResult = TaskUpdateResult | ModalActionResult | dict[str, object] | None


MessageHandler = Callable[..., Awaitable[None] | None]


class PluginAction(Protocol):
    plugin_id: str
    action_id: str
    label: str
    surface: str
    form_id: str | None


class PluginForm(Protocol):
    plugin_id: str
    form_id: str
    fields: list[dict[str, object]]


class PluginBadge(Protocol):
    surface: str
    label: str
    icon: str | None


class PluginUICatalog(Protocol):
    schema_version: str
    actions: list[PluginAction]
    forms: list[PluginForm]
    badges: list[PluginBadge]


class ChatTargetKind(Protocol):
    key: str
    kind: str
    label: str
    task_id: str | None
