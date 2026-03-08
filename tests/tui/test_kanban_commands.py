import pytest

from kagan.tui.screens.kanban import KanbanScreen
from kagan.tui.screens.kanban_commands import KANBAN_COMMANDS

pytestmark = [pytest.mark.tui]


def test_task_import_github_command_targets_existing_action() -> None:
    spec = next(item for item in KANBAN_COMMANDS if item.command == "task.import-github")
    assert spec.action == "import_github"
    assert hasattr(KanbanScreen, f"action_{spec.action}")


def test_all_kanban_commands_target_existing_screen_actions() -> None:
    for spec in KANBAN_COMMANDS:
        assert hasattr(KanbanScreen, f"action_{spec.action}")
