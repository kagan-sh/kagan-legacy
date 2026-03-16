import inspect
from dataclasses import dataclass
from functools import partial
from typing import Any

from textual.command import DiscoveryHit, Hit, Hits, Provider


@dataclass(frozen=True, slots=True)
class KanbanCommandSpec:
    command: str
    help: str
    action: str
    requires_task: bool = False


KANBAN_COMMANDS: tuple[KanbanCommandSpec, ...] = (
    KanbanCommandSpec("task.new", "Create a new task", "new_task"),
    KanbanCommandSpec("task.new-auto", "Create a new AUTO task", "new_auto_task"),
    KanbanCommandSpec(
        "task.open", "Open selected task session", "open_session", requires_task=True
    ),
    KanbanCommandSpec("task.edit", "Edit selected task", "edit_task", requires_task=True),
    KanbanCommandSpec(
        "task.details", "View selected task details", "open_session", requires_task=True
    ),
    KanbanCommandSpec(
        "task.delete", "Delete selected task", "delete_task_direct", requires_task=True
    ),
    KanbanCommandSpec(
        "task.duplicate", "Duplicate selected task", "duplicate_task", requires_task=True
    ),
    KanbanCommandSpec("agent.start", "Start AUTO agent", "start_agent", requires_task=True),
    KanbanCommandSpec("agent.stop", "Stop AUTO agent", "stop_agent", requires_task=True),
    KanbanCommandSpec("task.import-github", "Import issues from GitHub", "import_github"),
    KanbanCommandSpec("task.move-left", "Move selected task left", "move_left", requires_task=True),
    KanbanCommandSpec(
        "task.move-right", "Move selected task right", "move_right", requires_task=True
    ),
    KanbanCommandSpec(
        "task.set-branch", "Set selected task base branch", "set_branch", requires_task=True
    ),
    KanbanCommandSpec("view.search", "Toggle board search", "search"),
    KanbanCommandSpec("view.assistant-cycle", "Cycle assistant split", "toggle_chat"),
    KanbanCommandSpec(
        "view.assistant-fullscreen",
        "Toggle fullscreen AI Assistant",
        "fullscreen_chat",
    ),
    KanbanCommandSpec("view.settings", "Open settings", "open_settings"),
    KanbanCommandSpec("view.repo-sync", "Refresh repository/task state", "sync_repo"),
)


def _run_screen_action(screen: Any, action: str) -> None:
    action_method = getattr(screen, f"action_{action}", None)
    if action_method is None:
        return
    result = action_method()
    if inspect.isawaitable(result):
        screen.run_worker(result)


def _command_available(screen: Any, item: KanbanCommandSpec) -> bool:
    if not item.requires_task:
        return True
    return screen._selected_task() is not None


class KanbanCommandProvider(Provider):
    async def search(self, query: str) -> Hits:
        screen = self.screen
        matcher = self.matcher(query)
        for item in KANBAN_COMMANDS:
            if not _command_available(screen, item):
                continue
            score = matcher.match(item.command)
            if score <= 0:
                continue
            yield Hit(
                score,
                matcher.highlight(item.command),
                partial(_run_screen_action, screen, item.action),
                help=item.help,
            )

    async def discover(self) -> Hits:
        screen = self.screen
        for item in KANBAN_COMMANDS:
            if not _command_available(screen, item):
                continue
            yield DiscoveryHit(
                item.command,
                partial(_run_screen_action, screen, item.action),
                help=item.help,
            )
